"""A probe's own status, from the Devices page.

Every Setpoint probe serves a small web page (``/``) and a JSON status
(``/status``) on the LAN, but nothing in the hub pointed at either, so seeing a
probe's firmware version, power mode or upload backlog meant knowing its IP and
typing it in. The Devices card now links to the page, and a Details button has
the HUB fetch ``/status`` — which also works when the dashboard itself is being
viewed from away (over Tailscale), where the probe's own address is unreachable.

The probe is looked up by id in the hub's own discovery table, never from an
address the browser sends, and only a LAN address is ever fetched — the same
rule the provisioner follows before it sends the device token anywhere.
"""
from __future__ import annotations

import datetime
from typing import List, Optional, Tuple

from core.netaddr import checked_lan_target, is_lan_address
from core.probes import discovered_probes, probe_address, probe_port

# How long a deep-sleeping probe keeps its web server up after each report
# (WEBSERVER_WINDOW_MS in the firmware), for the "it did not answer" message.
BATTERY_LISTEN_SEC = 3


def probe_page_url(addr: str, port) -> Optional[str]:
    """``http://addr[:port]/`` for a probe the browser can open, else None.

    Only a LAN IP literal or a ``.local`` name gets a link — mDNS is where these
    come from, and a link to anything else would be a link off the network.
    """
    addr = str(addr or "").strip().rstrip(".")
    if not addr or addr in ("N/A", "via readings"):
        return None
    if not (addr.endswith(".local") or is_lan_address(addr)):
        return None
    try:
        port = int(port or 80)
    except (TypeError, ValueError):
        port = 80
    return f"http://{addr}/" if port == 80 else f"http://{addr}:{port}/"


def find_probe(finder, probe_id: str) -> Optional[Tuple[str, int]]:
    """``(host, port)`` the hub discovered for ``probe_id``, or None."""
    for p in discovered_probes(finder):
        if p.get("probe_id") == probe_id:
            host = probe_address(p)
            if host:
                return host, probe_port(p)
    return None


def fetch_probe_status(host: str, port: int, getter=None) -> Optional[dict]:
    """The probe's ``/status`` JSON, or None (off-LAN, asleep, or unreachable)."""
    target = checked_lan_target(host)
    if target is None:
        return None
    if getter is None:
        from provisioning import get_probe_status as getter
    try:
        return getter(target, port)
    except Exception:  # noqa: BLE001 - an unreachable probe is an answer, not an error
        return None


def _secs(ms) -> str:
    try:
        s = float(ms) / 1000.0
    except (TypeError, ValueError):
        return ""
    if s < 60:
        return f"{s:g} s"
    if s < 3600:
        return f"{s / 60:g} min"
    return f"{s / 3600:g} h"


def status_rows(st: dict) -> List[Tuple[str, str]]:
    """``[(label, value)]`` for the details panel, in plain words.

    Only fields the probe actually sent are shown: older firmware omits some,
    and a row reading "None" would look like a fault.
    """
    rows: List[Tuple[str, str]] = []

    def add(label, value):
        if value not in (None, ""):
            rows.append((label, str(value)))

    add("Firmware", st.get("fw_version"))
    add("Probe ID", st.get("probe_id") or st.get("id"))
    add("MAC address", st.get("mac"))
    mode = st.get("sleep_mode")
    if mode is not None:
        add("Power mode", "Battery (deep sleep between reports)"
            if "deep" in str(mode).lower() else "Always on (USB)")
    if st.get("temperature_c") is not None:
        try:
            add("Last reading", f"{float(st['temperature_c']):.2f} °C"
                + (f" at {st['timestamp']}" if st.get("timestamp") else ""))
        except (TypeError, ValueError):
            pass
    if st.get("time_valid") is not None:
        add("Clock", "Set from the network" if st.get("time_valid")
            else "Not set yet (readings stamped by the hub)")
    add("Reports every", _secs(st.get("interval_ms")) if st.get("interval_ms") else None)
    if st.get("watch_armed") is not None:
        add("Checks between reports",
            f"every {_secs(st.get('sample_ms'))}" if st.get("watch_armed") else "Off")
    lo, hi = st.get("alert_min_c"), st.get("alert_max_c")
    if lo is not None or hi is not None:
        add("Limits on the probe", f"{'—' if lo is None else lo} to {'—' if hi is None else hi} °C")
    if st.get("in_breach") is not None:
        add("Out of range now", "Yes" if st.get("in_breach") else "No")
    if st.get("buffered_est_rows") is not None:
        n = int(st.get("buffered_est_rows") or 0)
        add("Readings waiting to upload", "None" if n == 0 else f"about {n}")
    free, total = st.get("fs_free_kb"), st.get("fs_total_kb")
    if free is not None and total:
        add("Storage free", f"{free} of {total} KB")
    # Only meaningful for a probe that sleeps; an always-on one reports 0 forever.
    if "deep" in str(mode or "").lower():
        add("Wake-ups since power on", st.get("wake_count"))
    add("Sends readings to", st.get("server_url"))
    return rows


def not_answering_message(probe_name: str) -> str:
    return (f"{probe_name} did not answer. A battery probe only listens for about "
            f"{BATTERY_LISTEN_SEC} seconds after each report, so try again just after its "
            f"next reading arrives. An always-on (USB) probe should answer any time — "
            f"check it has power and is on your Wi-Fi.")


def checked_at() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")
