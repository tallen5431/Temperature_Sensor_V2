"""Waitress's queue-depth stream, and where the customer's log actually goes.

A burst that saturates the worker pool — twenty probes draining buffered
readings at once after an outage, which is exactly when an operator is already
anxious — makes `waitress.queue` log a WARNING for *every queued request*. A
45-second synthetic burst produced **13,383 of them against 404 real hub lines**:
a 33:1 flood, in the ordinary logging format of a library the customer has never
heard of, describing successful backpressure. Nothing failed in that run.

Worse, it did not even land in `logs/hub.log`. Waitress logs to its own
top-level logger and the hub's handlers hang off the `hub` tree, so those
records reached the console through root's default handling and never reached
the file a customer is asked to send to support.

The same problem `probe_discovery._quiet_zeroconf_cache_race` solves for
zeroconf, and the same answer: keep the signal, drop the repetition.
"""
import logging

import pytest

from core.logging_setup import _ThrottledQueueDepth, configure_logging


@pytest.fixture
def isolated_logging():
    """Snapshot and restore the loggers `configure_logging` mutates.

    Loggers are process-global. `configure_logging` clears handlers and sets
    `propagate = False`, which is right for the app and poison for a test
    session: pytest's caplog captures by propagation, so any test that ran after
    one of these lost its log records. It is only called from app.py in real
    use, so nothing noticed until these tests started calling it directly — and
    what broke were two OTHER modules' tests, several files away.
    """
    names = ("hub", "waitress", "waitress.queue")
    saved = {}
    for name in names:
        lg = logging.getLogger(name)
        saved[name] = (list(lg.handlers), list(lg.filters), lg.propagate,
                       lg.level, getattr(lg, "_configured", None))
    try:
        yield
    finally:
        for name in names:
            lg = logging.getLogger(name)
            handlers, filters, propagate, level, configured = saved[name]
            for h in list(lg.handlers):
                if h not in handlers:
                    h.close()
            lg.handlers[:] = handlers
            lg.filters[:] = filters
            lg.propagate = propagate
            lg.setLevel(level)
            if configured is None:
                if hasattr(lg, "_configured"):
                    delattr(lg, "_configured")
            else:
                lg._configured = configured


class _Clock:
    """A hand-wound clock, so these test the throttle rather than the ambient
    value of time.monotonic() — which counts from system BOOT and was 294 s in
    the container that first ran this, less than the 300 s interval."""

    def __init__(self, t=0.0):
        self.t = float(t)

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += float(seconds)


def _emit(n, filt, name="waitress.queue"):
    """Push n records through the filter; return how many survive."""
    kept = 0
    for i in range(n):
        rec = logging.LogRecord(name, logging.WARNING, __file__, i,
                                "Task queue depth is %d", (i,), None)
        if filt.filter(rec):
            kept += 1
    return kept


def test_a_burst_collapses_to_one_notice():
    assert _emit(13_383, _ThrottledQueueDepth(300, clock=_Clock())) == 1


def test_the_very_first_notice_is_never_swallowed():
    """`_last` seeded to 0.0 was compared against time.monotonic(), which counts
    from system BOOT — so on a machine less than one interval up, the first
    notice was dropped. That is exactly a hub set to start on boot or login, at
    the one moment it is most likely to be saturated: every probe rejoining at
    once. Caught because the container running these tests had been up 294 s."""
    for boot_age in (0.0, 1.0, 294.7, 299.9):
        filt = _ThrottledQueueDepth(300, clock=_Clock(boot_age))
        assert _emit(5, filt) == 1, f"first notice swallowed {boot_age}s after boot"


def test_the_notice_says_how_many_it_stood_for():
    """Dropping 13,000 lines silently would trade one wrong impression for
    another — the operator should still learn the hub was saturated."""
    clock = _Clock()
    filt = _ThrottledQueueDepth(300, clock=clock)
    _emit(500, filt)
    rec = logging.LogRecord("waitress.queue", logging.WARNING, __file__, 1,
                            "Task queue depth is %d", (9,), None)
    clock.advance(301)
    assert filt.filter(rec) is True
    text = rec.getMessage()
    assert "499 more" in text, text
    assert "keeping up" in text


def test_the_interval_reopens():
    clock = _Clock()
    filt = _ThrottledQueueDepth(300, clock=clock)
    assert _emit(50, filt) == 1
    assert _emit(50, filt) == 0, "the interval has not elapsed"
    clock.advance(301)
    assert _emit(50, filt) == 1


def test_every_other_waitress_record_passes_untouched():
    """A real serving error must never be hidden by a filter aimed at one
    chatty sub-logger."""
    filt = _ThrottledQueueDepth(300, clock=_Clock())
    _emit(100, filt)                       # exhaust the queue-depth budget
    for name in ("waitress", "waitress.error", "hub.app"):
        assert _emit(3, filt, name=name) == 3, name


def test_waitress_records_reach_the_hubs_own_handlers(tmp_path, isolated_logging):
    """They used to go to root, so they printed in a different format and never
    reached logs/hub.log — noise where it was useless, absent where it mattered."""
    root = logging.getLogger("hub")
    for attr in ("_configured",):
        if hasattr(root, attr):
            delattr(root, attr)
    root.handlers.clear()
    configure_logging(str(tmp_path))

    waitress = logging.getLogger("waitress")
    assert waitress.propagate is False, "still escaping to the root logger"
    assert waitress.handlers, "waitress has no handler of its own"
    hub_handlers = {id(h) for h in root.handlers}
    assert {id(h) for h in waitress.handlers} <= hub_handlers, \
        "waitress is writing somewhere other than the hub's own log"
    assert any(isinstance(h, logging.handlers.RotatingFileHandler)
               for h in waitress.handlers), \
        "waitress still never reaches logs/hub.log"


def test_the_throttle_is_attached_where_it_actually_runs(tmp_path, isolated_logging):
    """A logger's filters run in its own handle(); a record from a child only
    visits an ancestor's HANDLERS. Attached to `waitress` instead of
    `waitress.queue` this would have been inert, and the flood would have
    carried on through a fix that read correctly."""
    root = logging.getLogger("hub")
    if hasattr(root, "_configured"):
        delattr(root, "_configured")
    root.handlers.clear()
    configure_logging(str(tmp_path))
    queue_logger = logging.getLogger("waitress.queue")
    assert any(isinstance(f, _ThrottledQueueDepth) for f in queue_logger.filters), \
        "the throttle is not on waitress.queue, so it will never see a record"


def test_reconfiguring_does_not_stack_a_second_throttle(tmp_path, isolated_logging):
    """Loggers are process-global and survive a re-configure. Two throttles run
    independent intervals, so twice as much gets through — and it compounds."""
    root = logging.getLogger("hub")
    queue_logger = logging.getLogger("waitress.queue")
    queue_logger.filters.clear()
    for _ in range(3):
        if hasattr(root, "_configured"):
            delattr(root, "_configured")
        root.handlers.clear()
        configure_logging(str(tmp_path))
    throttles = [f for f in queue_logger.filters if isinstance(f, _ThrottledQueueDepth)]
    assert len(throttles) == 1, f"{len(throttles)} throttles stacked up"
