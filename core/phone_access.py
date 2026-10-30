"""The addresses a phone can open this hub's dashboard at, and a QR code for one.

"Use the hub computer's IP address" is an instruction that assumes someone can
find the IP address. The dashboard already knows it, so it shows it — as a QR
code a phone camera can open in one tap, plus the ``setpoint.local`` name that
survives the router handing the PC a new IP, plus the Tailscale address when the
PC is on a tailnet, which is the one that also works away from home.
"""
from __future__ import annotations

import ipaddress
import socket
from typing import List, Optional
from urllib.parse import urlsplit

from core.mdns_advert import hub_hostname

_TAILNET = ipaddress.ip_network("100.64.0.0/10")


def local_ipv4_addresses() -> List[str]:
    """This machine's IPv4 addresses, best effort and without extra packages."""
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:
        return []
    return sorted({i[4][0] for i in infos})


def access_urls(public_base: str, mdns_enabled: bool = True,
                local_ips: Optional[List[str]] = None) -> List[dict]:
    """``[{label, url, note}]`` in the order a person should try them.

    ``public_base`` is the address the hub hands to probes, so it is by
    construction one this LAN can reach. Loopback is never offered: a phone
    scanning ``http://127.0.0.1`` would be pointed at itself.
    """
    parts = urlsplit(public_base or "")
    port = parts.port or 80
    suffix = "" if port == 80 else f":{port}"
    out = []
    host = parts.hostname or ""
    if host and not host.startswith("127.") and host != "localhost":
        out.append({"label": "On this Wi-Fi", "url": f"http://{host}{suffix}",
                    "note": "Works on any phone or laptop on the same network."})
    if mdns_enabled:
        name = hub_hostname().rstrip(".")
        out.append({"label": "By name", "url": f"http://{name}{suffix}",
                    "note": "Keeps working if the PC's address changes. iPhone, Mac "
                            "and Windows understand it; some Android phones do not."})
    for ip in local_ips if local_ips is not None else local_ipv4_addresses():
        try:
            if ipaddress.ip_address(ip) in _TAILNET:
                out.append({"label": "Away from home (Tailscale)",
                            "url": f"http://{ip}{suffix}",
                            "note": "Works anywhere on a phone signed in to the same "
                                    "Tailscale account."})
                break
        except ValueError:
            continue
    return out


def qr_data_uri(text: str) -> Optional[str]:
    """An SVG QR code for ``text`` as a data: URI, or None without ``segno``.

    segno is optional like openpyxl: a hub without it still lists the addresses,
    it just cannot draw the code. Rendered dark-on-light with a quiet zone —
    phone cameras struggle with an inverted code on the dashboard's dark theme.
    """
    try:
        import segno
    except ImportError:
        return None
    # svg_data_uri, not svg_inline: the inline form omits the xmlns attribute
    # (correct inside an HTML page, where the parser supplies it), and an <img>
    # source without it does not render at all — the dashboard showed only the
    # alt text.
    return segno.make(text, error="m").svg_data_uri(scale=6, border=4,
                                                     dark="#000", light="#fff")
