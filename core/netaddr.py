"""Is this address somewhere the hub may send its device token?

The hub's auto-provisioner POSTs the device token — the credential that lets a
caller write readings into the log — to every probe discovery hands it. The
address it uses comes from an mDNS record broadcast by any device on the network,
so "where discovery says the probe is" and "where the token may go" are not the
same question, and the second one needs an answer of its own.

``api/routes.py`` already reasons about this on the ingest path, and says why:

    Use ONLY the transport-observed peer address — never a `host` from the body.
    A body-supplied hostname lands in the discovery registry, and the
    auto-provisioner then resolves it and POSTs the hub's device token to
    whatever it points at, which would let any client that can reach
    /api/ingest exfiltrate the token to an off-LAN address.

That closed the ingest route into the registry. The mDNS route was left open: a
service record's ``server`` field was taken verbatim, resolved with
``getaddrinfo`` — which falls through to unicast DNS for anything outside
``.local`` — and handed to the provisioner. A record advertising
``collector.example.net`` therefore resolved to a public address and received the
token.

It does not take an attacker, either. An ISP resolver with wildcard NXDOMAIN
hijacking answers *every* name, including a probe hostname that has momentarily
stopped resolving over mDNS, and the token goes to an ad server.

SECURITY.md's threat model is "another device/user on the same LAN", and every
limitation it lists is LAN-local in its consequence. This one was not: it turns
transient presence on the network into a credential that works from anywhere.
"""
from __future__ import annotations

import ipaddress

# Ranges a probe can legitimately be reached on. Deliberately explicit rather
# than `ipaddress.is_private`, which answers a different question and gets both
# ends of this one wrong: it calls 203.0.113.0/24 (RFC 5737 documentation space)
# private, and it calls 100.64.0.0/10 public — the range Tailscale hands out, so
# a perfectly ordinary overlay deployment would be refused.
_LAN_NETS = tuple(ipaddress.ip_network(n) for n in (
    "127.0.0.0/8",        # loopback — hub and probe on one machine, and tests
    "10.0.0.0/8",         # RFC 1918
    "172.16.0.0/12",
    "192.168.0.0/16",
    "169.254.0.0/16",     # RFC 3927 link-local (no DHCP)
    "100.64.0.0/10",      # RFC 6598 shared address space — Tailscale, CGNAT
    "::1/128",            # IPv6 loopback
    "fc00::/7",           # IPv6 unique-local
    "fe80::/10",          # IPv6 link-local
))

# mDNS resolves names inside this domain and no other (RFC 6762 §3). A
# _temps-probe._tcp.local. record whose host is outside it is malformed, whatever
# the intent behind it.
MDNS_SUFFIX = ".local"


def is_lan_address(value) -> bool:
    """True when ``value`` is an IP literal inside a range a probe can live on.

    A hostname returns False — resolve it first and check the result, so the
    answer is about where the packet actually goes.
    """
    try:
        addr = ipaddress.ip_address(str(value).strip().rstrip("."))
    except (TypeError, ValueError):
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped        # ::ffff:203.0.113.7 is not a LAN address
    return any(addr in net for net in _LAN_NETS)


def is_mdns_hostname(value) -> bool:
    """True for a name mDNS is entitled to have answered — i.e. one in ``.local``.

    An IP literal is accepted too: a record may advertise an address directly,
    and :func:`is_lan_address` is what judges that.
    """
    host = str(value or "").strip().rstrip(".").lower()
    if not host:
        return False
    if is_lan_address(host):
        return True
    return host.endswith(MDNS_SUFFIX) and len(host) > len(MDNS_SUFFIX)


def checked_lan_target(host, resolver=None):
    """The LAN address the hub may send its device token to, or ``None``.

    Returns the ADDRESS, not just a verdict, so the caller can send to the exact
    thing that was checked. Resolving once here and again at the point of sending
    is two answers to one question, and a hostile mDNS responder only has to make
    them differ — it says a LAN address while being checked and a public one a
    moment later. Handing back the verified address removes the second lookup,
    and with it the window.

    A ``.local`` name that answers with an off-LAN address is refused exactly
    like an off-domain one: the check is on where the packet goes, not on how the
    name is spelled. ``resolver`` is injected for testing; it defaults to the
    bounded resolver the provisioner already uses.
    """
    host = str(host or "").strip().rstrip(".")
    if not host:
        return None
    if is_lan_address(host):
        return host                     # already an address; nothing to resolve
    if not is_mdns_hostname(host):
        return None
    if resolver is None:
        from provisioning import resolve_host as resolver
    resolved = resolver(host)
    return resolved if is_lan_address(resolved) else None


def token_safe_target(host, resolver=None) -> bool:
    """May the hub send its device token to ``host``? See :func:`checked_lan_target`,
    which this is the yes/no form of."""
    return checked_lan_target(host, resolver) is not None
