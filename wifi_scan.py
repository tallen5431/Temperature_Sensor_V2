# wifi_scan.py
"""
Cross-platform SSID scanner (best-effort).
Tries Windows (netsh), macOS (airport), Linux (nmcli/iwlist). No admin needed.
Exposes:
  - scan_ssids() -> set[str]
  - SSIDWatcher: background refresher with latest set
"""
from __future__ import annotations
import os, subprocess, sys, threading, shutil, re, time
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

_MACOS_AIRPORT = ("/System/Library/PrivateFrameworks/Apple80211.framework"
                  "/Versions/Current/Resources/airport")


def _macos_airport() -> str:
    """Path to the macOS scanner, or "" if this Mac no longer has one.

    Apple removed the `airport` binary in macOS 14.4 (Sonoma). On a newer Mac
    there is nothing here to run, which is not the same as "no networks nearby"
    — see :func:`scanner_available`.
    """
    if shutil.which("airport"):
        return "airport"
    return _MACOS_AIRPORT if os.path.exists(_MACOS_AIRPORT) else ""


def scanner_available() -> bool:
    """Can this machine scan for Wi-Fi networks at all?

    Distinct from "did the scan find anything". A hub with no scanner returns an
    empty set from :func:`scan_ssids` exactly like a hub that scanned and saw
    nothing, and the setup helper used to report both as "Setpoint-XXXXXX: not
    found" — telling a customer to go power-cycle a probe that was very possibly
    already broadcasting, on a machine that could never have seen it.

    It is not a rare case: the hub is meant to live on an always-on mini-PC,
    which is usually wired; macOS 14.4 removed the scanner outright; and a
    Raspberry Pi OS Lite install has neither nmcli nor iwlist by default.
    """
    if sys.platform.startswith("win"):
        return bool(shutil.which("netsh"))
    if sys.platform == "darwin":
        return bool(_macos_airport())
    return bool(shutil.which("nmcli") or shutil.which("iwlist"))


def scan_ssids() -> Set[str]:
    if sys.platform.startswith("win"):
        out = _run(["netsh", "wlan", "show", "networks", "mode=Bssid"])
        if out:
            return _parse_windows(out)
        return set()
    # macOS
    if sys.platform == "darwin":
        airport = _macos_airport()
        out = _run([airport, "-s"]) if airport else ""
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

    def __init__(self, target_ssid: str, interval_sec: float = 5.0,
                 idle_timeout_sec: float = 0.0):
        self.target = target_ssid
        self.interval = interval_sec
        # Stop scanning by itself if nothing has asked for results in this long.
        # The explicit stop() only fires when the UI section is COLLAPSED, and
        # Dash does not dispatch callbacks for components that unmount -- so
        # navigating away from Settings, closing the tab, or a browser crash all
        # left the thread shelling out to netsh/nmcli every few seconds for the
        # life of the hub process, on a module-level singleton shared by every
        # client. Each poll for results is a keepalive (see ``start``); 0
        # disables the expiry.
        self.idle_timeout = float(idle_timeout_sec or 0.0)
        self._last_touch = time.monotonic()
        self.latest: Set[str] = set()
        # Has a scan actually completed since start()? Until one has, "no
        # networks seen" is not yet a fact about the airwaves, only about how
        # recently the section was opened.
        self.scanned = False
        self._stop = threading.Event()
        # Serialises the commit of a scan result against stop(). scan_ssids()
        # shells out with a 5 s subprocess timeout, so without this the worker
        # can finish a scan, be stopped mid-flight, and then write its result
        # over the cleared state -- leaving the watcher stopped but holding a
        # sighting from before the stop, which is exactly what stop()'s
        # docstring says must not happen. A retired thread could also clobber a
        # live one's fresh answer the same way.
        self._lock = threading.Lock()
        self._th: threading.Thread | None = None

    def start(self) -> None:
        # Already scanning — nothing to do. The `not self._stop.is_set()` half
        # matters: after a stop() the previous thread can still be alive for a
        # moment while it winds down, and treating that as "already running"
        # would return without starting anything, leaving a watcher that looks
        # started and never scans again.
        # Every call is also a keepalive: the caller polling for results is what
        # proves someone is still watching. See idle_timeout.
        self._last_touch = time.monotonic()
        if self._th and self._th.is_alive() and not self._stop.is_set():
            return
        # A FRESH event per thread, closed over by the loop. Re-using one event
        # and clearing it could revive a thread that had already decided to exit
        # (or leave a new thread racing a stale set flag); this way a retired
        # thread keeps its own set event and dies, and the new one starts clean.
        self._stop = stop = threading.Event()

        def _loop():
            while not stop.is_set():
                if self.idle_timeout and \
                        (time.monotonic() - self._last_touch) > self.idle_timeout:
                    # THIS thread's event, not the public stop(). start() swaps
                    # in a fresh event per thread, so an expiring thread calling
                    # stop() can set the event of a thread that started
                    # microseconds ago — killing the scan someone is actively
                    # watching, and clearing its results. Under the lock, and
                    # only while this thread is still the current one.
                    with self._lock:
                        if self._stop is not stop:
                            return          # superseded; leave the new one alone
                        stop.set()
                        self._stop.set()
                        self.latest = set()
                        self.scanned = False
                    return
                try:
                    found = scan_ssids()
                except Exception:
                    found = set()
                # Scan outside the lock (it blocks for seconds), commit inside
                # it, and re-check THIS thread's own event while holding it --
                # so a result can never land after the stop that discarded it.
                with self._lock:
                    if stop.is_set():
                        return
                    self.latest = found
                    self.scanned = True
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
        with self._lock:
            self.latest = set()
            self.scanned = False

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
