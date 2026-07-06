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
    name: str                 # e.g. ThermaProbe-9A3F2C
    host: str                 # e.g. thermaprobe-9a3f2c.local.
    ip: str                   # resolved IPv4 string
    port: int                 # advertised port (80)
    properties: Dict[str, str] = field(default_factory=dict)
    last_seen: float = field(default_factory=time.time)
    service_name: str = ""    # full mDNS instance name (exact key for removal)
    source: str = "mdns"      # "mdns" or "ingest"

class ProbeDiscovery:
    def __init__(self):
        self._zc = Zeroconf()
        self._browser = None
        self._lock = threading.RLock()
        self._probes: Dict[str, ProbeInfo] = {}  # key by host (mdns) or probe_id (ingest)
        self.on_change: Optional[Callable[[Dict[str, ProbeInfo]], None]] = None

    def _resolve_ip(self, host: str) -> Optional[str]:
        try:
            # Resolve mDNS host with timeout to prevent hanging
            import socket as sock_module
            host_clean = host.rstrip(".")
            old_timeout = sock_module.getdefaulttimeout()
            try:
                sock_module.setdefaulttimeout(3.0)
                result = sock_module.getaddrinfo(host_clean, None, sock_module.AF_INET)
                if result and len(result) > 0:
                    return result[0][4][0]  # Extract IP address from first result
                return None
            finally:
                sock_module.setdefaulttimeout(old_timeout)
        except Exception:
            return None

    def _info_to_probe(self, info: ServiceInfo) -> Optional[ProbeInfo]:
        try:
            host = info.server or ""
            ip = self._resolve_ip(host) or ""
            props = {}
            for k, v in (info.properties or {}).items():
                try:
                    key = k.decode() if isinstance(k, (bytes, bytearray)) else str(k)
                    props[key] = v.decode() if isinstance(v, (bytes, bytearray)) else str(v)
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
                service_name=info.name or "",
                source="mdns",
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
                self._probes[probe.host] = probe
                snapshot = dict(self._probes)
            if self.on_change:
                self.on_change(snapshot)

        elif state_change == ServiceStateChange.Removed:
            with self._lock:
                # Remove ONLY the probe whose full mDNS instance name matches
                # exactly. The previous `name.startswith(p.name)` could delete a
                # different probe whose name was a prefix of the one going away.
                to_delete = [
                    key for key, p in self._probes.items()
                    if p.source == "mdns" and (p.service_name == name or key == name)
                ]
                for key in to_delete:
                    self._probes.pop(key, None)
                snapshot = dict(self._probes)
            if self.on_change:
                self.on_change(snapshot)

    # --- zeroconf callback compatibility wrapper ---
    def _handle_compat(self, *args, **kwargs):
        zc = kwargs.get('zeroconf') or kwargs.get('zc')
        stype = kwargs.get('service_type') or kwargs.get('stype')
        name = kwargs.get('name')
        state_change = kwargs.get('state_change')
        if zc is None and len(args) >= 1: zc = args[0]
        if stype is None and len(args) >= 2: stype = args[1]
        if name is None and len(args) >= 3: name = args[2]
        if state_change is None and len(args) >= 4: state_change = args[3]
        return self._handle(zc, stype, name, state_change)

    def register_seen(self, probe_id: str, ip: str = "", port: int = 80, host: str = "") -> None:
        """Record that a probe just POSTed data.

        If the probe was already discovered over mDNS, we only refresh its
        last_seen/ip. Otherwise (mDNS blocked by a firewall, but ingest works)
        we create an entry keyed by probe_id so it still appears in the UI.
        This mutates the REAL probe dict under lock — the old ingest code
        mutated a throwaway copy from list_probes(), so posting-only probes and
        last_seen updates were silently lost.
        """
        if not probe_id:
            return
        now = time.time()
        with self._lock:
            for p in self._probes.values():
                pid = (p.properties or {}).get("id") or p.name
                if pid == probe_id or p.name == probe_id:
                    p.last_seen = now
                    if ip:
                        p.ip = ip
                    return
            self._probes[probe_id] = ProbeInfo(
                name=probe_id,
                host=host or ip or "",
                ip=ip,
                port=port or 80,
                properties={"id": probe_id},
                last_seen=now,
                service_name="",
                source="ingest",
            )

    def start(self):
        if self._browser:
            return
        self._browser = ServiceBrowser(self._zc, SERVICE_TYPE, handlers=[self._handle_compat])

    def stop(self):
        try:
            if self._browser:
                self._browser.cancel()
        finally:
            self._browser = None
            self._zc.close()

    def scan(self):
        """Manual refresh: restart the browser to prompt immediate updates."""
        try:
            if self._browser:
                self._browser.cancel()
                self._browser = None
            self._browser = ServiceBrowser(self._zc, SERVICE_TYPE, handlers=[self._handle_compat])
        except Exception:
            pass

    def list_probes(self) -> Dict[str, ProbeInfo]:
        with self._lock:
            return dict(self._probes)
