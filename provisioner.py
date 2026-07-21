from __future__ import annotations
import logging
import threading, time, socket
from typing import Callable, Optional, Any
from provisioning import provision_probe, get_probe_status, clamp_resolution_bits

log = logging.getLogger("hub.provisioner")


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
        cfg=None,
    ):
        super().__init__(daemon=True)
        self.discovery = discovery
        self.public_base_func = public_base_func
        self.token = token or ""
        self.interval_ms = int(interval_ms)
        self.period_sec = int(period_sec)
        self.cfg = cfg
        self._stop = False
        # Probes we've pushed our config to at least once this session. The
        # status-check shortcut below can't see a probe's token (/status never
        # exposes it), so a probe with the right server_url+interval but a
        # stale/absent token — e.g. right after the hub first generates its
        # device token — would match the shortcut and never receive the token,
        # 401ing on every ingest forever. Forcing one provision per probe per
        # session guarantees the current token is delivered at least once.
        self._provisioned: set = set()

    def stop(self):
        self._stop = True

    def _refresh_ip_best_effort(self, key: str, p) -> Optional[str]:
        """Resolve probe hostname to a fresh IP (best-effort).

        Returns the new IP string if the address changed, otherwise None.
        Never mutates the probe object directly — callers must use
        discovery.update_probe_ip() under the discovery lock.
        """
        try:
            mdns_host = (p.get("host") if isinstance(p, dict) else getattr(p, "host", "")) or ""
            mdns_host = mdns_host.rstrip(".")
            if not mdns_host:
                return None
            new_ip = _resolve_with_timeout(mdns_host)
            cur_ip = p.get("ip") if isinstance(p, dict) else getattr(p, "ip", None)
            if new_ip and new_ip != cur_ip:
                return new_ip
        except Exception:
            pass
        return None

    def run(self):
        while not self._stop:
            try:
                # Evict probes that have been gone long enough that they should
                # no longer occupy the Devices list (bounds memory over time).
                try:
                    prune_after = 3600
                    if self.cfg is not None:
                        prune_after = int(self.cfg.get("probe_prune_after_sec", 3600) or 3600)
                    self.discovery.prune_stale(prune_after)
                except Exception:
                    pass

                base = (self.public_base_func() or "").rstrip("/")
                if base:
                    for key, p in (self.discovery.list_probes() or {}).items():
                        # 1) Best-effort refresh of IP in case DHCP changed it.
                        # update_probe_ip acquires the discovery lock internally.
                        new_ip = self._refresh_ip_best_effort(key, p)
                        if new_ip:
                            self.discovery.update_probe_ip(key, new_ip)

                        # 2) Handle both dict and object-style probes
                        if isinstance(p, dict):
                            props = p.get("properties", {}) or {}
                            probe_id = props.get("id") or p.get("probe_id") or p.get("id")
                            host = new_ip or p.get("ip") or p.get("host") or ""
                            port = int(p.get("port", 80) or 80)
                        else:
                            props = getattr(p, "properties", {}) or {}
                            probe_id = props.get("id") or getattr(p, "probe_id", None) or getattr(p, "id", None)
                            host = new_ip or getattr(p, "ip", None) or getattr(p, "host", None) or ""
                            port = int(getattr(p, "port", 80) or 80)

                        # Per-probe interval override from config, falling back to global default
                        interval_ms = self.interval_ms
                        resolution_bits = None
                        if self.cfg is not None and probe_id:
                            try:
                                interval_value = (self.cfg.get("probe_intervals") or {}).get(probe_id)
                                if interval_value is not None:
                                    interval_ms = int(float(interval_value) * 1000)
                            except Exception:
                                pass
                            # Per-probe DS18B20 resolution override, else the global default.
                            try:
                                global_res = self.cfg.get("resolution_bits", 11)
                                res_value = (self.cfg.get("probe_resolutions") or {}).get(probe_id, global_res)
                                resolution_bits = clamp_resolution_bits(res_value)
                            except Exception:
                                resolution_bits = None

                        host = (host or "").rstrip(".")
                        if host:
                            target_url = f"{base}/api/ingest"
                            # Once we've provisioned this probe this session, only
                            # re-provision when its visible config (server_url /
                            # interval) differs — this avoids the ESP32 doing an
                            # NVS write (slow, brief stall) every cycle when nothing
                            # has changed. Until then, always push so the current
                            # token reaches it (the status shortcut can't see the
                            # token; see _provisioned in __init__).
                            if key in self._provisioned:
                                try:
                                    status = get_probe_status(host, port)
                                    # resolution_bits may be absent on older firmware
                                    # — treat absent as a match so it doesn't force a
                                    # re-provision every cycle.
                                    res_ok = status.get("resolution_bits") in (None, resolution_bits) \
                                        if status else False
                                    if (status and
                                            status.get("server_url") == target_url and
                                            status.get("interval_ms") == interval_ms and
                                            res_ok):
                                        continue  # already configured correctly
                                except Exception:
                                    pass  # can't check — fall through and provision

                            try:
                                if provision_probe(
                                    host,
                                    port,
                                    base,
                                    token=self.token,
                                    interval_ms=interval_ms,
                                    resolution_bits=resolution_bits,
                                ):
                                    self._provisioned.add(key)
                            except Exception as e:
                                # best-effort; we'll retry next cycle
                                log.warning("Failed to provision %s:%s: %s", host, port, e)
            except Exception:
                log.exception("Error in provisioning cycle")

            time.sleep(self.period_sec)
