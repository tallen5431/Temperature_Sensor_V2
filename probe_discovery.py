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

class ProbeDiscovery:
    def __init__(self):
        self._zc = Zeroconf()
        self._browser = None
        self._lock = threading.RLock()
        self._probes: Dict[str, ProbeInfo] = {}  # key by host
        self.on_change: Optional[Callable[[Dict[str, ProbeInfo]], None]] = None

    def _resolve_ip(self, host: str) -> Optional[str]:
        try:
            # Resolve mDNS host with timeout to prevent hanging
            # socket.gethostbyname doesn't support timeout directly, so we use socket.getaddrinfo
            import socket as sock_module
            host_clean = host.rstrip(".")
            # Set default timeout for socket operations (3 seconds)
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
                self._probes[probe.host] = probe
                snapshot = dict(self._probes)
            if self.on_change:
                self.on_change(snapshot)

        elif state_change == ServiceStateChange.Removed:
            with self._lock:
                # name is like "TempSensor-9A3F._temps-probe._tcp.local."
                # We don’t always get host here; remove by prefix match
                to_delete = []
                for host, p in self._probes.items():
                    if name.startswith(p.name):
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
            # Best-effort; ignore
            pass

    def list_probes(self) -> Dict[str, ProbeInfo]:
        with self._lock:
            return dict(self._probes)
