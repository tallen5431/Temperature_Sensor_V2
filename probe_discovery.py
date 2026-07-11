# probe_discovery.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional
from zeroconf import ServiceBrowser, Zeroconf, ServiceStateChange, ServiceInfo
import socket
import threading
import time

SERVICE_TYPE = "_temps-probe._tcp.local."

@dataclass
class ProbeInfo:
    name: str                 # e.g. TempSensor-9A3F
    host: str                 # e.g. temps-probe-9a3f.local.
    ip: str                   # resolved IPv4 string
    port: int                 # advertised port (80)
    properties: Dict[str, str] = field(default_factory=dict)
    last_seen: float = field(default_factory=time.time)


def _probe_ip(p) -> str:
    return (p.get("ip") if isinstance(p, dict) else getattr(p, "ip", None)) or ""


def _probe_last_seen(p) -> float:
    v = p.get("last_seen") if isinstance(p, dict) else getattr(p, "last_seen", None)
    return float(v) if isinstance(v, (int, float)) else 0.0


def dedupe_probes_by_ip(probes: Dict[str, "ProbeInfo"]) -> Dict[str, "ProbeInfo"]:
    """Collapse entries that share a LAN IP down to the single freshest one.

    A single physical probe can transiently appear under two identities — e.g.
    the mDNS record advertised at boot (before the DS18B20 ROM is read) and the
    id it later POSTs to ``/api/ingest`` — which still share one LAN IP.  Keeping
    only the most recently-seen entry per IP means one device shows as one card
    (and is counted once in ``/api/health``).  Entries whose IP is unknown are
    passed through untouched, and the surviving entry keeps its real dict key so
    callers (provisioner, IP refresh) can still address it.
    """
    winners: Dict[str, tuple] = {}   # ip -> (key, probe)
    out: Dict[str, "ProbeInfo"] = {}
    for key, p in probes.items():
        ip = _probe_ip(p)
        if not ip:
            out[key] = p
            continue
        cur = winners.get(ip)
        if cur is None or _probe_last_seen(p) > _probe_last_seen(cur[1]):
            winners[ip] = (key, p)
    for key, p in winners.values():
        out[key] = p
    return out


class ProbeDiscovery:
    def __init__(self):
        self._zc = Zeroconf()
        self._browser = None
        self._lock = threading.RLock()
        self._probes: Dict[str, ProbeInfo] = {}  # key by host
        self.on_change: Optional[Callable[[Dict[str, ProbeInfo]], None]] = None

    def _resolve_ip(self, host: str) -> Optional[str]:
        """Resolve mDNS hostname to IP using a background thread to avoid
        mutating the global socket timeout (which is not thread-safe)."""
        host_clean = host.rstrip(".")
        result_holder: list = [None]

        def _do_resolve():
            try:
                res = socket.getaddrinfo(host_clean, None, socket.AF_INET)
                if res:
                    result_holder[0] = res[0][4][0]
            except Exception:
                pass

        t = threading.Thread(target=_do_resolve, daemon=True)
        t.start()
        t.join(3.0)
        return result_holder[0]

    def _info_to_probe(self, info: ServiceInfo) -> Optional[ProbeInfo]:
        try:
            host = info.server or ""
            ip = self._resolve_ip(host) or ""
            props = {}
            for k, v in (info.properties or {}).items():
                try:
                    props[k.decode()] = v.decode() if isinstance(v, (bytes, bytearray)) else str(v)
                except Exception:
                    pass
            name = (props.get("name") or info.name or host).replace("." + SERVICE_TYPE, "")
            return ProbeInfo(
                name=name,
                host=host,
                ip=ip,
                port=info.port or 80,
                properties=props,
                last_seen=time.time(),
            )
        except Exception:
            return None

    def _handle(self, zc: Zeroconf, stype: str, name: str, state_change: ServiceStateChange):
        if state_change == ServiceStateChange.Added or state_change == ServiceStateChange.Updated:
            info = zc.get_service_info(stype, name)
            if not info:
                return
            probe = self._info_to_probe(info)
            if not probe:
                return
            with self._lock:
                # Remove any stale entry that was created by update_last_seen
                # before mDNS discovery completed (keyed by probe_id rather than
                # host).  Without this, the same probe produces two cards.
                probe_id = probe.properties.get('id', '')
                if probe_id:
                    stale = [k for k, p in self._probes.items()
                             if k != probe.host and (
                                 (isinstance(p, dict) and
                                  (p.get('name') == probe_id or
                                   (p.get('properties') or {}).get('id') == probe_id))
                                 or
                                 (not isinstance(p, dict) and
                                  (p.name == probe_id or
                                   (p.properties or {}).get('id') == probe_id))
                             )]
                    for k in stale:
                        del self._probes[k]
                self._probes[probe.host] = probe
                snapshot = dict(self._probes)
            if self.on_change:
                self.on_change(snapshot)

        elif state_change == ServiceStateChange.Removed:
            with self._lock:
                # name is like "TempSensor-9A3F._temps-probe._tcp.local."
                # Match only when the probe name is followed by "." or is an
                # exact match, so "TempSensor-9A" never removes "TempSensor-9A3F".
                to_delete = []
                for host, p in self._probes.items():
                    probe_name = p.name if not isinstance(p, dict) else p.get('name', '')
                    if name == probe_name or name.startswith(probe_name + "."):
                        to_delete.append(host)
                for host in to_delete:
                    self._probes.pop(host, None)
                snapshot = dict(self._probes)
            if self.on_change:
                self.on_change(snapshot)
    # --- zeroconf callback compatibility wrapper ---
    def _handle_compat(self, *args, **kwargs):
        """Accept both new-style keyword args (zeroconf=..., service_type=..., name=..., state_change=...)
        and old-style positional args, then forward to the original _handle.
        """
        zc = kwargs.get('zeroconf') or kwargs.get('zc')
        stype = kwargs.get('service_type') or kwargs.get('stype')
        name = kwargs.get('name')
        state_change = kwargs.get('state_change')
        # Fill missing from positional args
        if zc is None and len(args) >= 1: zc = args[0]
        if stype is None and len(args) >= 2: stype = args[1]
        if name is None and len(args) >= 3: name = args[2]
        if state_change is None and len(args) >= 4: state_change = args[3]
        # Call _handle with all 4 required parameters
        return self._handle(zc, stype, name, state_change)

    def start(self):
        if self._browser:
            return
        self._browser = ServiceBrowser(self._zc, SERVICE_TYPE, handlers=[self._handle_compat])

    def stop(self):
        browser, self._browser = self._browser, None
        if browser:
            try:
                browser.cancel()
                browser.join(timeout=2.0)
            except Exception:
                pass
        try:
            self._zc.close()
        except Exception:
            pass

    def scan(self):
        """Manual refresh: restart the browser to prompt immediate updates."""
        try:
            old_browser, self._browser = self._browser, None
            if old_browser:
                old_browser.cancel()
                old_browser.join(timeout=1.0)
            self._browser = ServiceBrowser(self._zc, SERVICE_TYPE, handlers=[self._handle_compat])
        except Exception:
            # Best-effort; ignore
            pass

    def list_probes(self) -> Dict[str, ProbeInfo]:
        with self._lock:
            snapshot = dict(self._probes)
        # Collapse a probe that is transiently known under two identities (e.g.
        # an mDNS record plus the id it POSTs on ingest) to one entry per IP.
        return dedupe_probes_by_ip(snapshot)

    def prune_stale(self, max_age_sec: float = 3600.0) -> int:
        """Drop probes not seen within max_age_sec so the table stays bounded.

        Returns the number of entries removed.  Recently-offline probes are kept
        (the UI shows them greyed out); only long-gone devices are evicted.
        """
        cutoff = time.time() - max_age_sec
        removed = 0
        with self._lock:
            for key in list(self._probes.keys()):
                p = self._probes[key]
                last = p.get("last_seen") if isinstance(p, dict) else getattr(p, "last_seen", None)
                if isinstance(last, (int, float)) and last < cutoff:
                    del self._probes[key]
                    removed += 1
        return removed

    def forget_probe(self, probe_id: str) -> int:
        """Drop every discovery entry matching ``probe_id`` (by name or its 'id'
        TXT property). Returns the number of entries removed.

        Used by "remove device". Note this only forgets the CURRENT discovery
        state — a probe that is still powered on will re-register on its next
        mDNS announcement or ingest, which is the honest behavior (you can't
        make a live, broadcasting device disappear from the LAN).
        """
        pid = (probe_id or "").strip()
        if not pid:
            return 0
        removed = 0
        with self._lock:
            for key in list(self._probes.keys()):
                p = self._probes[key]
                if isinstance(p, dict):
                    name = p.get("name")
                    prop_id = (p.get("properties") or {}).get("id")
                else:
                    name = getattr(p, "name", None)
                    prop_id = (getattr(p, "properties", {}) or {}).get("id")
                if pid in (key, name, prop_id):
                    del self._probes[key]
                    removed += 1
        return removed

    def update_probe_ip(self, key: str, new_ip: str) -> None:
        """Atomically update a probe's IP address under the discovery lock."""
        with self._lock:
            p = self._probes.get(key)
            if p is None:
                return
            if isinstance(p, dict):
                p["ip"] = new_ip
                p["last_seen"] = time.time()
            else:
                p.ip = new_ip
                p.last_seen = time.time()

    def update_last_seen(self, probe_id: str, host: str = "", ip: str = "") -> None:
        """Mark a probe as recently seen (called on ingest). If the probe is not
        yet known via mDNS, register a minimal entry so it appears in the UI."""
        with self._lock:
            for p in self._probes.values():
                p_name = getattr(p, 'name', None) if not isinstance(p, dict) else p.get('name')
                p_prop_id = (getattr(p, 'properties', {}) or {}).get('id') if not isinstance(p, dict) else (p.get('properties') or {}).get('id')
                if p_name == probe_id or p_prop_id == probe_id:
                    if isinstance(p, dict):
                        p['last_seen'] = time.time()
                    else:
                        p.last_seen = time.time()
                    return
            # Probe not yet known — add a minimal entry keyed by probe_id
            self._probes[probe_id] = ProbeInfo(
                name=probe_id,
                host=host or probe_id,
                ip=ip,
                port=80,
                properties={'id': probe_id},
                last_seen=time.time(),
            )
