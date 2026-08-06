"""`ProbeDiscovery` — the class that turns mDNS traffic off the LAN into the
probe list every screen is built from.

`test_discovery.py` covers `dedupe_probes_by_ip` and the registry cap; the class
itself was at 35% — the highest-risk untested code in the repo, because it is the
only module that parses bytes it did not produce, arriving from any host on the
network, before they reach the Devices grid, `/api/probes`, Diagnostics and the
auto-provisioner (which will then POST the hub's device token to what it finds).

These drive it without opening a multicast socket: `_handle` is called with
stand-in `ServiceInfo` objects exactly as zeroconf would, and every registry
mutator is exercised directly.
"""
import threading
import time

import probe_discovery
from probe_discovery import ProbeInfo, SERVICE_TYPE


class Disco(probe_discovery.ProbeDiscovery):
    """ProbeDiscovery with no Zeroconf — no sockets, no threads, CI-safe."""

    def __init__(self):
        self._zc = None
        self._browser = None
        self._lock = threading.RLock()
        self._probes = {}
        self.on_change = None

    def _resolve_ip(self, host):          # no DNS in a unit test
        return self.fake_ips.get(host, "")

    fake_ips: dict = {}


class Info:
    """The shape of zeroconf's ServiceInfo that `_info_to_probe` reads."""

    def __init__(self, server, name=None, port=80, properties=None):
        self.server = server
        self.name = name or server
        self.port = port
        self.properties = properties or {}


class Zc:
    """Stand-in for the Zeroconf handle `_handle` is given."""

    def __init__(self, info=None):
        self.info = info

    def get_service_info(self, stype, name):
        return self.info


def _disco(ips=None):
    d = Disco()
    d.fake_ips = dict(ips or {})
    return d


def _added(d, info, zc=None):
    d._handle(zc or Zc(info), SERVICE_TYPE, info.name,
              probe_discovery.ServiceStateChange.Added)


# --- parsing a service record ----------------------------------------------

def test_a_txt_record_becomes_a_probe():
    d = _disco({"Setpoint-9A3F2C.local.": "192.168.1.40"})
    _added(d, Info("Setpoint-9A3F2C.local.", port=80,
                   properties={b"id": b"Setpoint-9A3F2C", b"name": b"Walk-in"}))
    (probe,) = d.list_probes().values()
    assert probe.name == "Walk-in"
    assert probe.ip == "192.168.1.40"
    assert probe.properties["id"] == "Setpoint-9A3F2C"


def test_undecodable_txt_values_do_not_lose_the_whole_probe():
    """TXT records arrive as bytes from any host on the LAN. One key that is not
    UTF-8 must cost that key, not the probe — the record still identifies a real
    device that the operator needs to see."""
    d = _disco({"p.local.": "10.0.0.5"})
    _added(d, Info("p.local.", properties={b"id": b"Setpoint-1",
                                           b"junk": b"\xff\xfe\x00bad"}))
    (probe,) = d.list_probes().values()
    assert probe.properties["id"] == "Setpoint-1"


def test_a_service_info_the_browser_cannot_resolve_is_ignored():
    """zeroconf returns None when the record does not resolve in time. That is a
    normal event on a busy network, not a probe."""
    d = _disco()
    d._handle(Zc(None), SERVICE_TYPE, "ghost." + SERVICE_TYPE,
              probe_discovery.ServiceStateChange.Added)
    assert d.list_probes() == {}


def test_a_probe_that_never_resolves_to_an_ip_is_still_listed():
    """An unresolvable hostname is worth showing — the operator can see the probe
    is announcing itself and that name resolution is what is broken."""
    d = _disco()
    _added(d, Info("late.local.", properties={b"id": b"Setpoint-2"}))
    (probe,) = d.list_probes().values()
    assert probe.ip == "" and probe.host == "late.local."


def test_the_id_falls_back_through_name_then_host():
    d = _disco()
    _added(d, Info("bare.local.", name="bare." + SERVICE_TYPE))
    (probe,) = d.list_probes().values()
    assert probe.name == "bare", "the service-type suffix should be stripped"


# --- the two identities one probe can hold ---------------------------------

def test_an_ingest_only_entry_is_replaced_when_mdns_finds_the_same_probe():
    """A probe that POSTs before mDNS resolves is registered under its probe_id;
    the later mDNS record is keyed by host. Without the merge the same physical
    device renders as two cards."""
    d = _disco({"Setpoint-9A3F2C.local.": "192.168.1.40"})
    d.update_last_seen("Setpoint-9A3F2C", ip="192.168.1.40")
    assert len(d._probes) == 1
    _added(d, Info("Setpoint-9A3F2C.local.",
                   properties={b"id": b"Setpoint-9A3F2C"}))
    assert len(d._probes) == 1, f"one device, two entries: {list(d._probes)}"
    (probe,) = d.list_probes().values()
    assert probe.host == "Setpoint-9A3F2C.local."


def test_a_different_probe_is_not_swallowed_by_the_merge():
    d = _disco({"Setpoint-AAA.local.": "10.0.0.1"})
    d.update_last_seen("Setpoint-BBB", ip="10.0.0.2")
    _added(d, Info("Setpoint-AAA.local.", properties={b"id": b"Setpoint-AAA"}))
    assert len(d._probes) == 2


# --- removal ---------------------------------------------------------------

def test_a_removed_service_drops_its_probe():
    d = _disco({"p.local.": "10.0.0.5"})
    _added(d, Info("p.local.", name="Setpoint-9A3F2C." + SERVICE_TYPE,
                   properties={b"id": b"Setpoint-9A3F2C", b"name": b"Setpoint-9A3F2C"}))
    d._handle(Zc(), SERVICE_TYPE, "Setpoint-9A3F2C." + SERVICE_TYPE,
              probe_discovery.ServiceStateChange.Removed)
    assert d.list_probes() == {}


def test_a_prefix_match_never_removes_a_longer_named_probe():
    """"Setpoint-9A" leaving must not take "Setpoint-9A3F2C" with it. The guard
    is the reason the match requires a following "." or an exact equality."""
    d = _disco()
    for pid in ("Setpoint-9A", "Setpoint-9A3F2C"):
        _added(d, Info(f"{pid}.local.", name=f"{pid}.{SERVICE_TYPE}",
                       properties={b"id": pid.encode(), b"name": pid.encode()}))
    assert len(d._probes) == 2
    d._handle(Zc(), SERVICE_TYPE, "Setpoint-9A." + SERVICE_TYPE,
              probe_discovery.ServiceStateChange.Removed)
    names = {p.name for p in d._probes.values()}
    assert names == {"Setpoint-9A3F2C"}, f"prefix removal took a sibling: {names}"


# --- the zeroconf callback shim --------------------------------------------

def test_the_callback_shim_accepts_both_calling_conventions():
    """zeroconf has called handlers positionally and by keyword across versions;
    `_handle_compat` exists so an upgrade cannot silently stop discovery."""
    seen = []
    d = _disco()
    d._handle = lambda zc, stype, name, change: seen.append((stype, name, change))

    d._handle_compat(Zc(), SERVICE_TYPE, "a." + SERVICE_TYPE,
                     probe_discovery.ServiceStateChange.Added)
    d._handle_compat(zeroconf=Zc(), service_type=SERVICE_TYPE,
                     name="b." + SERVICE_TYPE,
                     state_change=probe_discovery.ServiceStateChange.Added)
    assert [s[1] for s in seen] == ["a." + SERVICE_TYPE, "b." + SERVICE_TYPE]
    assert all(s[0] == SERVICE_TYPE for s in seen)


# --- registry housekeeping --------------------------------------------------

def test_prune_drops_only_the_long_gone():
    d = _disco()
    now = time.time()
    d._probes = {
        "fresh": ProbeInfo("fresh", "fresh.local.", "10.0.0.1", 80, {}, now),
        "napping": ProbeInfo("napping", "nap.local.", "10.0.0.2", 80, {}, now - 600),
        "gone": ProbeInfo("gone", "gone.local.", "10.0.0.3", 80, {}, now - 90000),
    }
    assert d.prune_stale(3600) == 1
    assert set(d._probes) == {"fresh", "napping"}


def test_prune_tolerates_an_entry_with_no_timestamp():
    """Registry entries come from two sources and one may predate the field. A
    missing last_seen must not throw, and must not evict — the safer reading."""
    d = _disco()
    d._probes = {"odd": {"name": "odd", "ip": "10.0.0.9"}}
    assert d.prune_stale(1) == 0
    assert "odd" in d._probes


def test_forget_matches_the_key_the_name_or_the_txt_id():
    for key, probe, target in (
        ("k1", ProbeInfo("n1", "h1", "10.0.0.1", 80, {}, time.time()), "k1"),
        ("k2", ProbeInfo("n2", "h2", "10.0.0.2", 80, {}, time.time()), "n2"),
        ("k3", ProbeInfo("n3", "h3", "10.0.0.3", 80, {"id": "i3"}, time.time()), "i3"),
    ):
        d = _disco()
        d._probes = {key: probe}
        assert d.forget_probe(target) == 1, f"{target} did not match {key}"
        assert d._probes == {}


def test_forget_ignores_an_empty_id_rather_than_clearing_the_registry():
    d = _disco()
    d._probes = {"k": ProbeInfo("n", "h", "10.0.0.1", 80, {}, time.time())}
    assert d.forget_probe("") == 0 and d.forget_probe(None) == 0
    assert d.forget_probe("   ") == 0
    assert len(d._probes) == 1


def test_update_probe_ip_moves_the_address_and_refreshes_last_seen():
    d = _disco()
    d._probes = {"k": ProbeInfo("n", "h", "10.0.0.1", 80, {}, time.time() - 500)}
    d.update_probe_ip("k", "10.0.0.99")
    assert d._probes["k"].ip == "10.0.0.99"
    assert time.time() - d._probes["k"].last_seen < 5
    d.update_probe_ip("no-such-key", "10.0.0.1")     # must not raise or create


def test_update_last_seen_refreshes_by_name_or_by_txt_id():
    for props, target in (({}, "n"), ({"id": "i"}, "i")):
        d = _disco()
        old = time.time() - 500
        d._probes = {"k": ProbeInfo("n", "h", "10.0.0.1", 80, props, old)}
        d.update_last_seen(target)
        assert d._probes["k"].last_seen > old
        assert len(d._probes) == 1, "refreshing registered a duplicate"


def test_update_last_seen_refuses_to_register_a_nameless_phantom():
    """An empty id would create an entry keyed "" that renders as a blank card
    and counts toward the probe totals."""
    d = _disco()
    for junk in ("", "   ", None):
        d.update_last_seen(junk)
    assert d._probes == {}


def test_eviction_takes_the_oldest_and_keeps_the_newest(monkeypatch):
    monkeypatch.setattr(probe_discovery, "_MAX_PROBES", 3)
    d = _disco()
    for i in range(3):
        d._probes[f"p{i}"] = ProbeInfo(f"p{i}", f"h{i}", f"10.0.0.{i}", 80, {},
                                       time.time() - (100 - i))
    d.update_last_seen("newcomer", ip="10.0.0.9")
    assert "p0" not in d._probes, "the oldest entry survived the cap"
    assert "newcomer" in d._probes
    assert len(d._probes) <= 3


# --- lifecycle on a host with no usable network ----------------------------

def test_start_scan_and_stop_are_safe_with_no_zeroconf():
    """`Zeroconf()` raises on a container without host networking, and the class
    degrades to an inert object rather than taking ingest down. Every entry point
    has to survive that state — a raise here kills hub startup."""
    d = _disco()
    d.start()
    d.scan()
    d.stop()
    assert d.list_probes() == {}


def test_on_change_fires_with_a_snapshot_not_the_live_map():
    """The callback runs outside the lock. Handing over the live dict would let a
    consumer iterate it while the zeroconf thread mutates it."""
    d = _disco({"p.local.": "10.0.0.5"})
    seen = []
    d.on_change = seen.append
    _added(d, Info("p.local.", properties={b"id": b"Setpoint-1"}))
    assert len(seen) == 1 and len(seen[0]) == 1
    d._probes.clear()
    assert len(seen[0]) == 1, "the callback was handed the live registry"


def test_a_flood_of_records_cannot_grow_the_registry_without_bound(monkeypatch):
    """The mDNS counterpart of the ingest flood guard: `_handle` must respect the
    ceiling too, or a hostile (or broken) device on the LAN announcing thousands
    of service names grows the map forever."""
    monkeypatch.setattr(probe_discovery, "_MAX_PROBES", 25)
    d = _disco()
    for i in range(300):
        _added(d, Info(f"h{i}.local.", properties={b"id": f"p{i}".encode()}))
    assert len(d._probes) <= 25, f"registry grew to {len(d._probes)}"


def test_a_probe_with_a_friendly_name_can_still_be_removed():
    """The removal used to be matched against ProbeInfo.name, which is the TXT
    `name` key — PROTOCOL.md §3 defines that as "friendly name, else probe_id",
    a HUMAN label equal to the id only by convention. The shipping firmware sets
    them equal (`g_instanceName = g_probeId`), so the match worked by
    coincidence. Give a probe the friendly name the protocol expressly allows and
    its Removed event matched nothing: the probe stayed on the Devices grid and
    in the hub's probe total until the hourly prune eventually noticed."""
    d = _disco({"Setpoint-9A3F2C.local.": "10.0.0.5"})
    svc = "Setpoint-9A3F2C." + SERVICE_TYPE
    _added(d, Info("Setpoint-9A3F2C.local.", name=svc,
                   properties={b"id": b"Setpoint-9A3F2C", b"name": b"Walk-in Cooler"}))
    assert len(d._probes) == 1
    d._handle(Zc(), SERVICE_TYPE, svc, probe_discovery.ServiceStateChange.Removed)
    assert d._probes == {}, "a probe with a friendly name never leaves the registry"


def test_removal_matches_an_entry_registered_from_ingest_alone():
    """A probe the hub only knows from its POSTs is keyed by probe_id and has no
    TXT record at all. Its mDNS departure must still clear it."""
    d = _disco()
    d.update_last_seen("Setpoint-9A3F2C", ip="10.0.0.5")
    d._handle(Zc(), SERVICE_TYPE, "Setpoint-9A3F2C." + SERVICE_TYPE,
              probe_discovery.ServiceStateChange.Removed)
    assert d._probes == {}


def test_removal_still_refuses_to_take_a_probe_with_a_shared_prefix():
    """The property the old prefix match existed to protect, now free: identities
    are compared whole, so no id can be a prefix of another's."""
    d = _disco()
    for pid in ("Setpoint-9A", "Setpoint-9A3F2C"):
        _added(d, Info(f"{pid}.local.", name=f"{pid}.{SERVICE_TYPE}",
                       properties={b"id": pid.encode(), b"name": b"Some Cooler"}))
    d._handle(Zc(), SERVICE_TYPE, "Setpoint-9A." + SERVICE_TYPE,
              probe_discovery.ServiceStateChange.Removed)
    assert {p.properties["id"] for p in d._probes.values()} == {"Setpoint-9A3F2C"}


def test_a_removal_for_an_unknown_service_changes_nothing():
    d = _disco()
    d.update_last_seen("Setpoint-AAA", ip="10.0.0.1")
    d._handle(Zc(), SERVICE_TYPE, "Setpoint-ZZZ." + SERVICE_TYPE,
              probe_discovery.ServiceStateChange.Removed)
    assert len(d._probes) == 1


def test_the_service_label_helper_handles_what_zeroconf_actually_sends():
    from probe_discovery import _service_label
    assert _service_label("Setpoint-9A3F2C." + SERVICE_TYPE) == "Setpoint-9A3F2C"
    assert _service_label("Setpoint-9A3F2C") == "Setpoint-9A3F2C"
    assert _service_label("") == ""
    assert _service_label(None) == ""


def test_an_empty_service_name_never_clears_the_registry():
    """`label` empty must match nothing — an empty string is "in" very little,
    but a truthiness slip here would empty the whole grid."""
    d = _disco()
    d.update_last_seen("Setpoint-AAA", ip="10.0.0.1")
    for junk in ("", None, "   ", "."):
        d._handle(Zc(), SERVICE_TYPE, junk,
                  probe_discovery.ServiceStateChange.Removed)
    assert len(d._probes) == 1


# --- lifecycle against a stand-in Zeroconf ---------------------------------

class FakeBrowser:
    made = []

    def __init__(self, zc, stype, handlers=None):
        self.cancelled = False
        self.joined = False
        FakeBrowser.made.append(self)

    def cancel(self):
        self.cancelled = True

    def join(self, timeout=None):
        self.joined = True


class FakeZc:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def _wired(monkeypatch):
    monkeypatch.setattr(probe_discovery, "ServiceBrowser", FakeBrowser)
    FakeBrowser.made = []
    d = _disco()
    d._zc = FakeZc()
    return d


def test_start_is_idempotent(monkeypatch):
    """The Devices page and the provisioner both call it; a second browser on the
    same service type means every record handled twice."""
    d = _wired(monkeypatch)
    d.start()
    d.start()
    assert len(FakeBrowser.made) == 1


def test_scan_replaces_the_browser_and_retires_the_old_one(monkeypatch):
    d = _wired(monkeypatch)
    d.start()
    first = d._browser
    d.scan()
    assert first.cancelled and first.joined, "the old browser was left running"
    assert d._browser is not first and len(FakeBrowser.made) == 2


def test_stop_closes_the_browser_and_the_zeroconf_handle(monkeypatch):
    d = _wired(monkeypatch)
    d.start()
    browser, zc = d._browser, d._zc
    d.stop()
    assert browser.cancelled and zc.closed and d._browser is None


def test_stop_is_safe_twice_and_after_a_failed_start(monkeypatch):
    """cleanup() runs on every shutdown path, including ones where startup never
    completed. A raise here would mask the real error that caused the shutdown."""
    d = _wired(monkeypatch)
    d.stop()
    d.stop()


def test_a_browser_that_throws_on_cancel_does_not_break_shutdown(monkeypatch):
    class Angry(FakeBrowser):
        def cancel(self):
            raise RuntimeError("socket already gone")

    monkeypatch.setattr(probe_discovery, "ServiceBrowser", Angry)
    d = _disco()
    d._zc = FakeZc()
    d.start()
    d.stop()
    assert d._zc.closed, "a failing browser stopped the zeroconf handle closing"


# --- the zeroconf log-noise filter -----------------------------------------
# python-zeroconf can raise KeyError from its own DNSCache cleanup, which
# asyncio prints at ERROR with a full traceback naming some unrelated host on the
# LAN. The filter downgrades exactly that shape. If it over-matched it would
# silence real faults in the hub's own asyncio work, which is the failure mode
# worth pinning.

class Loop:
    def __init__(self, prev=None):
        self._handler = None
        self._prev = prev
        self.defaulted = []

    def get_exception_handler(self):
        return self._prev

    def set_exception_handler(self, fn):
        self._handler = fn

    def default_exception_handler(self, context):
        self.defaulted.append(context)


def _raise_from(filename):
    """A KeyError whose traceback passes through a frame in `filename`."""
    code = compile("def f():\n    raise KeyError('6c999dba4d16.local.')\n",
                   filename, "exec")
    ns = {}
    exec(code, ns)
    try:
        ns["f"]()
    except KeyError as e:
        return e


def test_the_filter_swallows_only_zeroconfs_own_cache_race():
    loop = Loop()
    probe_discovery._quiet_zeroconf_cache_race(loop)
    exc = _raise_from("/usr/lib/python3/zeroconf/_cache.py")
    loop._handler(loop, {"exception": exc})
    assert loop.defaulted == [], "the known-harmless race still reached the log"


def test_a_keyerror_from_the_hubs_own_code_is_not_silenced():
    loop = Loop()
    probe_discovery._quiet_zeroconf_cache_race(loop)
    exc = _raise_from("/home/hub/core/db.py")
    loop._handler(loop, {"exception": exc})
    assert len(loop.defaulted) == 1, "a real KeyError was swallowed as zeroconf noise"


def test_a_non_keyerror_from_zeroconf_is_not_silenced():
    loop = Loop()
    probe_discovery._quiet_zeroconf_cache_race(loop)

    def boom():
        raise ValueError("something actually broke")
    try:
        boom()
    except ValueError as e:
        loop._handler(loop, {"exception": e})
    assert len(loop.defaulted) == 1


def test_an_existing_exception_handler_is_chained_not_replaced():
    """Installing ours must not discard whatever else was already listening."""
    seen = []
    loop = Loop(prev=lambda lp, ctx: seen.append(ctx))
    probe_discovery._quiet_zeroconf_cache_race(loop)
    exc = _raise_from("/home/hub/app.py")
    loop._handler(loop, {"exception": exc})
    assert len(seen) == 1 and loop.defaulted == []


def test_a_context_with_no_exception_still_reaches_the_default_handler():
    loop = Loop()
    probe_discovery._quiet_zeroconf_cache_race(loop)
    loop._handler(loop, {"message": "socket.send() raised exception"})
    assert len(loop.defaulted) == 1


# --- hostname resolution ---------------------------------------------------
# Runs on its own thread deliberately: the obvious implementation sets
# socket.setdefaulttimeout() around the call, which is process-global and not
# thread-safe, so it would silently change the timeout of every other socket in
# the hub — ingest, SMTP, the forwarder — for the duration.

class Resolving(probe_discovery.ProbeDiscovery):
    def __init__(self):
        self._zc = None
        self._browser = None
        self._lock = threading.RLock()
        self._probes = {}
        self.on_change = None


def test_a_hostname_resolves_to_its_first_ipv4(monkeypatch):
    calls = []

    def fake(host, port, family):
        calls.append((host, family))
        return [(family, None, None, "", ("192.168.1.40", 0)),
                (family, None, None, "", ("192.168.1.41", 0))]

    monkeypatch.setattr(probe_discovery.socket, "getaddrinfo", fake)
    assert Resolving()._resolve_ip("Setpoint-9A3F2C.local.") == "192.168.1.40"
    assert calls[0][0] == "Setpoint-9A3F2C.local", "the trailing dot was not stripped"
    assert calls[0][1] == probe_discovery.socket.AF_INET, "asked for more than IPv4"


def test_a_name_that_does_not_resolve_returns_none_rather_than_raising(monkeypatch):
    def boom(*a, **k):
        raise OSError("Name or service not known")

    monkeypatch.setattr(probe_discovery.socket, "getaddrinfo", boom)
    assert Resolving()._resolve_ip("nope.local.") is None


def test_an_empty_result_is_not_an_index_error(monkeypatch):
    monkeypatch.setattr(probe_discovery.socket, "getaddrinfo", lambda *a, **k: [])
    assert Resolving()._resolve_ip("empty.local.") is None


def test_a_hung_resolver_gives_up_instead_of_blocking_discovery(monkeypatch):
    """`_handle` runs on zeroconf's callback thread. A resolver that never
    returns would wedge discovery for every probe behind it, so the wait is
    bounded and an unresolved probe is simply listed without an IP."""
    started = threading.Event()
    release = threading.Event()

    def hang(*a, **k):
        started.set()
        release.wait(30)
        return []

    monkeypatch.setattr(probe_discovery.socket, "getaddrinfo", hang)
    monkeypatch.setattr(probe_discovery.threading.Thread, "join",
                        lambda self, timeout=None: None)   # stand in for the 3 s cap
    assert Resolving()._resolve_ip("slow.local.") is None
    started.wait(5)
    release.set()


def test_resolution_does_not_touch_the_global_socket_timeout(monkeypatch):
    before = probe_discovery.socket.getdefaulttimeout()
    monkeypatch.setattr(probe_discovery.socket, "getaddrinfo",
                        lambda *a, **k: [(0, None, None, "", ("10.0.0.1", 0))])
    Resolving()._resolve_ip("x.local.")
    assert probe_discovery.socket.getdefaulttimeout() == before, (
        "the resolver changed the process-wide socket timeout, which every "
        "other socket in the hub shares")
