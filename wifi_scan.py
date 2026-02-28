# wifi_scan.py
"""
Cross-platform SSID scanner (best-effort).
Tries Windows (netsh), macOS (airport), Linux (nmcli/iwlist). No admin needed.
Exposes:
  - scan_ssids() -> set[str]
  - SSIDWatcher: background refresher with latest set
"""
from __future__ import annotations
import subprocess, sys, time, threading, shutil, re
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
        out = _run(["bash", "-lc", "iwlist scan"])
        if out:
            return _parse_iwlist(out)
    return set()

class SSIDWatcher:
    def __init__(self, target_ssid: str, interval_sec: float = 5.0):
        self.target = target_ssid
        self.interval = interval_sec
        self.latest: Set[str] = set()
        self._stop = threading.Event()
        self._th: threading.Thread | None = None

    def start(self) -> None:
        if self._th and self._th.is_alive():
            return
        def _loop():
            while not self._stop.is_set():
                try:
                    self.latest = scan_ssids()
                except Exception:
                    self.latest = set()
                time.sleep(self.interval)
        self._th = threading.Thread(target=_loop, daemon=True)
        self._th.start()

    def stop(self) -> None:
        self._stop.set()

    def seen(self) -> bool:
        return self.target in self.latest
