# wifi_scan.py
"""
Cross-platform SSID scanner (best-effort).
Tries Windows (netsh), macOS (airport), Linux (nmcli/iwlist). No admin needed.
Exposes:
  - scan_ssids() -> set[str]
  - SSIDWatcher: background refresher with latest set
"""
from __future__ import annotations
import subprocess, sys, threading, shutil, re
from typing import Set, List

def _run(cmd: List[str]) -> str:
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True, timeout=5)
        return out
    except Exception:
        return ""

def _parse_windows(text: str) -> Set[str]:
    # netsh wlan show networks mode=Bssid
    ssids: Set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if line.lower().startswith("ssid ") and ":" in line:
            # SSID 1 : MyWifi
            parts = line.split(":", 1)
            name = parts[1].strip()
            if name:
                ssids.add(name)
    return ssids

def _parse_macos(text: str) -> Set[str]:
    # airport -s
    ssids: Set[str] = set()
    for line in text.splitlines()[1:]:
        # SSID BSSID RSSI CHANNEL HT CC SECURITY (... variable spacing ...)
        name = line[:32].strip()  # SSID column is first 32 chars in default output
        if name:
            ssids.add(name)
    return ssids

def _parse_nmcli(text: str) -> Set[str]:
    # nmcli -t -f SSID dev wifi  (one per line, empty for hidden)
    ssids: Set[str] = set()
    for line in text.splitlines():
        if line.strip():
            ssids.add(line.strip())
    return ssids

def _parse_iwlist(text: str) -> Set[str]:
    # iwlist scan -> ESSID:"name"
    ssids: Set[str] = set(re.findall(r'ESSID:"([^"]+)"', text))
    return ssids

def scan_ssids() -> Set[str]:
    if sys.platform.startswith("win"):
        out = _run(["netsh", "wlan", "show", "networks", "mode=Bssid"])
        if out:
            return _parse_windows(out)
        return set()
    # macOS
    if sys.platform == "darwin":
        airport = "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport"
        if shutil.which("airport"):
            airport = "airport"
        out = _run([airport, "-s"])
        if out:
            return _parse_macos(out)
        return set()
    # Linux
    if shutil.which("nmcli"):
        out = _run(["nmcli", "-t", "-f", "SSID", "dev", "wifi"])
        if out:
            return _parse_nmcli(out)
    if shutil.which("iwlist"):
        out = _run(["iwlist", "scan"])
        if out:
            return _parse_iwlist(out)
    return set()

class SSIDWatcher:
    """Background SSID scanner that can be started and stopped repeatedly.

    Scanning shells out to netsh/nmcli/iwlist every ``interval_sec``, so it runs
    only while something is actually watching for a probe's setup network — the
    Settings page starts it when that section is opened and stops it when it is
    closed. Both halves of that have to work more than once, which is why
    ``start()`` clears the stop flag and ``stop()`` interrupts the sleep instead
    of leaving the thread to notice up to an interval later.
    """

    def __init__(self, target_ssid: str, interval_sec: float = 5.0):
        self.target = target_ssid
        self.interval = interval_sec
        self.latest: Set[str] = set()
        self._stop = threading.Event()
        self._th: threading.Thread | None = None

    def start(self) -> None:
        # Already scanning — nothing to do. The `not self._stop.is_set()` half
        # matters: after a stop() the previous thread can still be alive for a
        # moment while it winds down, and treating that as "already running"
        # would return without starting anything, leaving a watcher that looks
        # started and never scans again.
        if self._th and self._th.is_alive() and not self._stop.is_set():
            return
        # A FRESH event per thread, closed over by the loop. Re-using one event
        # and clearing it could revive a thread that had already decided to exit
        # (or leave a new thread racing a stale set flag); this way a retired
        # thread keeps its own set event and dies, and the new one starts clean.
        self._stop = stop = threading.Event()

        def _loop():
            while not stop.is_set():
                try:
                    self.latest = scan_ssids()
                except Exception:
                    self.latest = set()
                # wait(), not sleep(): stop() then takes effect at once rather
                # than after up to one full interval of further scanning.
                stop.wait(self.interval)

        self._th = threading.Thread(target=_loop, name="ssid-watcher", daemon=True)
        self._th.start()

    def stop(self) -> None:
        """Stop scanning and forget what was last seen.

        Dropping ``latest`` matters: the question this answers is "is the probe's
        setup network nearby *right now*", so a sighting from before the watcher
        was stopped must not be reported as current when it starts again.
        """
        self._stop.set()
        self.latest = set()

    def running(self) -> bool:
        return bool(self._th and self._th.is_alive() and not self._stop.is_set())

    def matched(self) -> List[str]:
        # The concrete SSIDs that matched — the exact target or any SSID that
        # begins with it, so a per-probe SoftAP like "Setpoint-9A3F2C" is
        # detected from the brand prefix "Setpoint". Sorted so the UI can tell
        # the user WHICH network to join.
        return sorted(s for s in self.latest
                      if s == self.target or s.startswith(self.target))

    def seen(self) -> bool:
        return bool(self.matched())
