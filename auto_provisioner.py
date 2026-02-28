from __future__ import annotations
import threading, time, socket
from typing import Callable, Optional
from auto_provision import provision_probe


def _resolve_with_timeout(host: str, timeout: float = 3.0) -> Optional[str]:
    """Resolve hostname to IP in a background thread to avoid blocking the caller."""
    result: list = [None]

    def _do():
        try:
            result[0] = socket.gethostbyname(host)
        except Exception:
            pass

    t = threading.Thread(target=_do, daemon=True)
    t.start()
    t.join(timeout)
    return result[0]


class AutoProvisioner(threading.Thread):
    """Background worker that keeps probes provisioned with the hub's ingest URL.

    It provisions each discovered probe by IP (preferred) with fallback to hostname.

    Enhancement:
      - Re-resolve p.host -> IP periodically so DHCP IP changes self-heal
        even when mDNS "Updated" events don't fire.
    """

    def __init__(
        self,
        discovery,
        public_base_func: Callable[[], str],
        token: str = "",
        interval_ms: int = 2000,
        period_sec: int = 10,
    ):
        super().__init__(daemon=True)
        self.discovery = discovery
        self.public_base_func = public_base_func
        self.token = token or ""
        self.interval_ms = int(interval_ms)
        self.period_sec = int(period_sec)
        self._stop = False

    def stop(self):
        self._stop = True

    def _refresh_ip_best_effort(self, p) -> None:
        """Try to refresh probe IP from its mDNS hostname (best-effort).
        Works for both dict-style and object-style probes.
        """
        try:
            if isinstance(p, dict):
                mdns_host = (p.get("host") or "").rstrip(".")
                if not mdns_host:
                    return
                new_ip = _resolve_with_timeout(mdns_host)
                if new_ip and new_ip != p.get("ip"):
                    p["ip"] = new_ip
                    p["last_seen"] = time.time()
            else:
                mdns_host = (getattr(p, "host", "") or "").rstrip(".")
                if not mdns_host:
                    return
                new_ip = _resolve_with_timeout(mdns_host)
                cur_ip = getattr(p, "ip", None)
                if new_ip and new_ip != cur_ip:
                    setattr(p, "ip", new_ip)
                    setattr(p, "last_seen", time.time())
        except Exception:
            # never let refresh break provisioning loop
            return

    def run(self):
        while not self._stop:
            try:
                base = (self.public_base_func() or "").rstrip("/")
                if base:
                    for p in (self.discovery.list_probes() or {}).values():
                        # 1) Best-effort refresh of IP in case DHCP changed it
                        self._refresh_ip_best_effort(p)

                        # 2) Handle both dict and object-style probes
                        if isinstance(p, dict):
                            host = p.get("ip") or p.get("host") or ""
                            port = int(p.get("port", 80) or 80)
                        else:
                            host = getattr(p, "ip", None) or getattr(p, "host", None) or ""
                            port = int(getattr(p, "port", 80) or 80)

                        host = (host or "").rstrip(".")
                        if host:
                            try:
                                provision_probe(
                                    host,
                                    port,
                                    base,
                                    token=self.token,
                                    interval_ms=self.interval_ms,
                                )
                            except Exception as e:
                                # best-effort; we'll retry next cycle
                                print(f"[auto_provisioner] Failed to provision {host}:{port}: {e}")
            except Exception as e:
                print(f"[auto_provisioner] Error in provisioning cycle: {e}")

            time.sleep(self.period_sec)
