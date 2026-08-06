"""Where the hub's device token is allowed to go.

The token is the credential that lets a caller write into the reading log. The
auto-provisioner POSTs it to every probe discovery hands it, and the address it
uses comes from an mDNS record broadcast by any device on the network.

`api/routes.py` already refuses a body-supplied hostname on the ingest path, and
its comment says exactly why: it "lands in the discovery registry, and the
auto-provisioner then resolves it and POSTs the hub's device token to whatever it
points at". That closed the ingest route in. The mDNS route was left open —
`info.server` was taken verbatim and resolved with `getaddrinfo`, which falls
through to unicast DNS for anything outside `.local`, so a record advertising
`collector.example.net` resolved to a public address and got the token.

No attacker is required, either: an ISP resolver with wildcard NXDOMAIN hijacking
answers every name, including a probe hostname that has momentarily stopped
resolving over mDNS, and the token goes to an ad server.

SECURITY.md's threat model is a device on the same LAN, and every limitation it
lists is LAN-local in its consequence. This one was not — it turns transient
presence on the network into a credential that works from anywhere.
"""
import threading

import pytest

import probe_discovery
from core.netaddr import is_lan_address, is_mdns_hostname, token_safe_target
from probe_discovery import SERVICE_TYPE

LAN = ["10.0.0.5", "192.168.1.40", "172.16.0.1", "172.31.255.254",
       "169.254.1.1", "127.0.0.1", "100.64.0.1", "::1", "fe80::1", "fd00::1"]
NOT_LAN = ["203.0.113.7", "8.8.8.8", "1.1.1.1", "172.32.0.1", "192.169.0.1",
           "2606:4700::1111", "::ffff:203.0.113.7"]


@pytest.mark.parametrize("addr", LAN)
def test_lan_ranges_are_accepted(addr):
    assert is_lan_address(addr) is True


@pytest.mark.parametrize("addr", NOT_LAN)
def test_routable_addresses_are_refused(addr):
    assert is_lan_address(addr) is False


def test_the_check_is_not_ipaddress_is_private():
    """`ipaddress.is_private` answers a different question and gets both ends of
    this one wrong — which is why the ranges are written out explicitly."""
    import ipaddress
    assert ipaddress.ip_address("203.0.113.7").is_private is True
    assert is_lan_address("203.0.113.7") is False, "documentation space is not a LAN"
    assert ipaddress.ip_address("100.64.0.1").is_private is False
    assert is_lan_address("100.64.0.1") is True, \
        "100.64/10 is what Tailscale hands out — refusing it breaks a real setup"


def test_an_ipv4_mapped_ipv6_address_cannot_smuggle_a_public_target():
    assert is_lan_address("::ffff:203.0.113.7") is False
    assert is_lan_address("::ffff:192.168.1.40") is True


def test_a_hostname_is_never_a_lan_address_on_its_own():
    """It has to be resolved first — the question is where the packet goes."""
    for host in ("probe.local", "evil.example.net", "localhost", ""):
        assert is_lan_address(host) is False


def test_only_dot_local_names_are_things_mdns_may_answer():
    assert is_mdns_hostname("Setpoint-9A3F2C.local.") is True
    assert is_mdns_hostname("Setpoint-9A3F2C.local") is True
    assert is_mdns_hostname("192.168.1.40") is True          # a literal is fine
    assert is_mdns_hostname("collector.example.net") is False
    assert is_mdns_hostname("evil.local.example.net") is False
    assert is_mdns_hostname(".local") is False               # suffix alone
    assert is_mdns_hostname("") is False and is_mdns_hostname(None) is False


# --- the gate in front of the token ----------------------------------------

def test_a_lan_literal_is_a_safe_target():
    assert token_safe_target("192.168.1.40", resolver=lambda h: None) is True


def test_an_off_domain_hostname_is_refused_without_even_resolving():
    calls = []
    assert token_safe_target("collector.example.net",
                             resolver=lambda h: calls.append(h) or "10.0.0.1") is False
    assert calls == [], "an off-domain name should be refused before any lookup"


def test_a_local_name_that_answers_off_lan_is_refused():
    """The case a hostname check alone misses: the name is well-formed, the
    ANSWER is not. A hostile mDNS responder, or a wildcard ISP resolver."""
    assert token_safe_target("Setpoint-9A3F2C.local",
                             resolver=lambda h: "203.0.113.7") is False


def test_a_local_name_that_answers_on_lan_is_accepted():
    assert token_safe_target("Setpoint-9A3F2C.local",
                             resolver=lambda h: "192.168.1.40") is True


def test_a_name_that_does_not_resolve_is_refused():
    assert token_safe_target("Setpoint-9A3F2C.local", resolver=lambda h: None) is False


def test_an_empty_target_is_refused():
    for junk in ("", None, "   ", "."):
        assert token_safe_target(junk, resolver=lambda h: "10.0.0.1") is False


# --- and the two places it is wired in --------------------------------------

class Disco(probe_discovery.ProbeDiscovery):
    def __init__(self, resolved):
        self._zc = None
        self._browser = None
        self._lock = threading.RLock()
        self._probes = {}
        self.on_change = None
        self._resolved = resolved

    def _resolve_ip(self, host):
        return self._resolved


class Info:
    def __init__(self, server, name, properties=None):
        self.server = server
        self.name = name
        self.port = 80
        self.properties = properties or {}


class Zc:
    def __init__(self, info):
        self.info = info

    def get_service_info(self, stype, name):
        return self.info


def _add(d, server):
    svc = "Setpoint-9A3F2C." + SERVICE_TYPE
    d._handle(Zc(Info(server, svc, {b"id": b"Setpoint-9A3F2C"})),
              SERVICE_TYPE, svc, probe_discovery.ServiceStateChange.Added)


def test_discovery_drops_a_record_advertising_a_host_outside_local():
    d = Disco(resolved="203.0.113.7")
    _add(d, "collector.example.net.")
    assert d.list_probes() == {}, \
        "an off-domain mDNS record reached the registry, and the provisioner"


def test_discovery_keeps_the_probe_but_drops_an_off_lan_answer():
    """A well-formed .local name whose lookup answers off-LAN: the probe is real
    enough to show — the operator should see it announcing itself — but the
    address must not travel any further."""
    d = Disco(resolved="203.0.113.7")
    _add(d, "Setpoint-9A3F2C.local.")
    (probe,) = d.list_probes().values()
    assert probe.ip == "", f"an off-LAN address was carried into the registry: {probe.ip}"
    assert probe.host == "Setpoint-9A3F2C.local."


def test_an_ordinary_probe_is_completely_unaffected():
    d = Disco(resolved="192.168.1.40")
    _add(d, "Setpoint-9A3F2C.local.")
    (probe,) = d.list_probes().values()
    assert probe.ip == "192.168.1.40"


def test_the_provisioner_refuses_an_off_lan_target(monkeypatch):
    """The backstop. Discovery already filters, but the address is re-resolved
    every cycle by _refresh_ip_best_effort, so the gate belongs where the secret
    is actually handed over as well."""
    import provisioner as provisioner_mod
    from probe_discovery import ProbeInfo

    sent = []
    monkeypatch.setattr(provisioner_mod, "provision_probe",
                        lambda host, port, base, **kw: sent.append(host) or True)
    monkeypatch.setattr(provisioner_mod, "usable_server_base", lambda base: True)

    class Finder:
        def __init__(self, ip):
            self._ip = ip

        def list_probes(self):
            import time as _t
            return {"k": ProbeInfo("Setpoint-9A3F2C", "Setpoint-9A3F2C.local.",
                                   self._ip, 80, {"id": "Setpoint-9A3F2C"}, _t.time())}

        def prune_stale(self, *a):
            return 0

        def update_probe_ip(self, *a):
            pass

    for ip, expected in (("203.0.113.7", []), ("192.168.1.40", ["192.168.1.40"])):
        sent.clear()
        ap = provisioner_mod.AutoProvisioner(
            Finder(ip), lambda: "http://192.168.1.2:8088", token="s3cr3t")
        ap._refresh_ip_best_effort = lambda key, p: None
        ap._run_cycle()
        assert sent == expected, f"target {ip}: token went to {sent}"


# --- one lookup, not two ---------------------------------------------------

def test_the_checked_address_is_handed_back_for_the_caller_to_use():
    """Returning a verdict alone left the caller to resolve the name a SECOND
    time at the point of sending. Two answers to one question is all a hostile
    mDNS responder needs: say a LAN address while being checked, a public one a
    moment later. The caller now sends to exactly what was verified."""
    from core.netaddr import checked_lan_target
    assert checked_lan_target("Setpoint-9A3F2C.local",
                              resolver=lambda h: "192.168.1.40") == "192.168.1.40"
    assert checked_lan_target("192.168.1.40", resolver=lambda h: None) == "192.168.1.40"
    assert checked_lan_target("Setpoint-9A3F2C.local",
                              resolver=lambda h: "203.0.113.7") is None
    assert checked_lan_target("collector.example.net",
                              resolver=lambda h: "192.168.1.40") is None


def test_the_provisioner_resolves_the_name_exactly_once(monkeypatch):
    """The window this closes: with two independent lookups, a resolver that
    flips its answer between them sends the token to the second one."""
    import provisioner as provisioner_mod
    from probe_discovery import ProbeInfo

    answers = iter(["192.168.1.40", "203.0.113.7", "203.0.113.7"])
    lookups = []

    def flipping(host, timeout=3.0):
        a = next(answers, "203.0.113.7")
        lookups.append((host, a))
        return a

    sent = []
    monkeypatch.setattr(provisioner_mod, "resolve_host", flipping)
    monkeypatch.setattr(provisioner_mod, "usable_server_base", lambda base: True)
    monkeypatch.setattr(provisioner_mod, "provision_probe",
                        lambda host, port, base, **kw: sent.append(host) or True)
    # core.netaddr resolves through provisioning.resolve_host by default.
    import provisioning
    monkeypatch.setattr(provisioning, "resolve_host", flipping)

    class Finder:
        def list_probes(self):
            import time as _t
            return {"k": ProbeInfo("Setpoint-9A3F2C", "Setpoint-9A3F2C.local.",
                                   "", 80, {"id": "Setpoint-9A3F2C"}, _t.time())}

        def prune_stale(self, *a):
            return 0

        def update_probe_ip(self, *a):
            pass

    ap = provisioner_mod.AutoProvisioner(
        Finder(), lambda: "http://192.168.1.2:8088", token="s3cr3t")
    ap._refresh_ip_best_effort = lambda key, p: None
    ap._run_cycle()

    assert sent == ["192.168.1.40"], (
        f"the token went somewhere other than the address that was checked: {sent}")
