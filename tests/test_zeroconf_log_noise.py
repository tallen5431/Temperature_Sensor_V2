"""The zeroconf cache-expiry race must not print tracebacks in a customer's log.

python-zeroconf raises KeyError from its own DNSCache cleanup when a record is
removed while async_expire() walks it. Nothing here can prevent it, but asyncio's
default handler prints it at ERROR with a traceback, so the hub log fills with
alarming noise from a library the customer has never heard of.
"""
import asyncio
import logging

from probe_discovery import _quiet_zeroconf_cache_race


def _raise_from(filename, exc):
    """Build an exception whose traceback passes through `filename`."""
    code = compile("def f():\n    raise exc\n", filename, "exec")
    ns = {"exc": exc}
    exec(code, ns)
    try:
        ns["f"]()
    except BaseException as e:  # noqa: BLE001
        return e
    raise AssertionError("unreachable")


def test_zeroconf_cache_keyerror_is_downgraded(caplog):
    loop = asyncio.new_event_loop()
    try:
        seen = []
        loop.set_exception_handler(lambda lp, ctx: seen.append(ctx))
        _quiet_zeroconf_cache_race(loop)
        exc = _raise_from("/x/zeroconf/_cache.py", KeyError("6c999dba4d16.local."))
        with caplog.at_level(logging.DEBUG, logger="hub.discovery"):
            loop.get_exception_handler()(loop, {"exception": exc, "message": "boom"})
        assert seen == [], "zeroconf cache KeyError should not reach the previous handler"
        assert any("cache-expiry race" in r.message for r in caplog.records)
    finally:
        loop.close()


def test_other_exceptions_still_surface():
    """Silencing everything would hide real faults — only that one shape goes."""
    loop = asyncio.new_event_loop()
    try:
        seen = []
        loop.set_exception_handler(lambda lp, ctx: seen.append(ctx))
        _quiet_zeroconf_cache_race(loop)
        # A KeyError from somewhere else must pass through.
        other = _raise_from("/x/core/db.py", KeyError("probe"))
        loop.get_exception_handler()(loop, {"exception": other, "message": "db"})
        # And so must a different exception type from zeroconf itself.
        zc_other = _raise_from("/x/zeroconf/_cache.py", ValueError("bad"))
        loop.get_exception_handler()(loop, {"exception": zc_other, "message": "zc"})
        assert len(seen) == 2
    finally:
        loop.close()
