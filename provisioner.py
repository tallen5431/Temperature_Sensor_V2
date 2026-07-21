from __future__ import annotations
import logging
import threading, time, socket
from typing import Callable, Optional, Any
from provisioning import provision_probe, get_probe_status, clamp_resolution_bits
from core.status import probe_fresh_window

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
        # Last successfully-pushed desired config per probe key:
        # (base, interval_ms, resolution_bits, token). When the desired tuple
        # is unchanged and the probe was provisioned this session, the cycle
        # skips even the /status verification GET (a resolver thread plus an
        # HTTP round-trip per probe per cycle). Only updated after
        # provision_probe() succeeds, so it can never record a config (or
        # token) as delivered that wasn't.
        self._pushed: dict = {}

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
                self._run_cycle()
            except Exception:
                log.exception("Error in provisioning cycle")

            time.sleep(self.period_sec)

    def _run_cycle(self):
        """One provisioning pass over the discovery list (factored out of
        :meth:`run` so tests can drive cycles synchronously)."""
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
        if not base:
            return

        # Derive the fallback interval from live config every cycle (when a
        # cfg is attached) so an operator's interval_sec change propagates
        # without a hub restart — the boot-time interval_ms is only the
        # default for cfg-less callers, not a value to keep reverting
        # probes to.
        default_interval_ms = self.interval_ms
        if self.cfg is not None:
            try:
                default_interval_ms = int(float(
                    self.cfg.get("interval_sec", self.interval_ms / 1000)) * 1000)
            except (TypeError, ValueError):
                pass

        now = time.time()
        for key, p in (self.discovery.list_probes() or {}).items():
            # 1) Handle both dict and object-style probes
            if isinstance(p, dict):
                props = p.get("properties", {}) or {}
                probe_id = props.get("id") or p.get("probe_id") or p.get("id")
                host = p.get("ip") or p.get("host") or ""
                port = int(p.get("port", 80) or 80)
                last_seen = p.get("last_seen")
            else:
                props = getattr(p, "properties", {}) or {}
                probe_id = props.get("id") or getattr(p, "probe_id", None) or getattr(p, "id", None)
                host = getattr(p, "ip", None) or getattr(p, "host", None) or ""
                port = int(getattr(p, "port", 80) or 80)
                last_seen = getattr(p, "last_seen", None)

            # 2) A probe silent longer than its fresh window is asleep (or
            # gone) — resolving and GETting it would just burn a 3 s
            # resolver thread plus an HTTP timeout every cycle. Skip it this
            # cycle; ingest/mDNS refresh last_seen, so a waking probe is
            # picked up on the next pass.
            if isinstance(last_seen, (int, float)):
                fresh_window = 3600.0
                if self.cfg is not None:
                    try:
                        fresh_window = float(probe_fresh_window(self.cfg, probe_id))
                    except Exception:
                        pass
                if (now - float(last_seen)) > fresh_window:
                    continue

            # 3) Best-effort refresh of IP in case DHCP changed it.
            # update_probe_ip acquires the discovery lock internally.
            new_ip = self._refresh_ip_best_effort(key, p)
            if new_ip:
                self.discovery.update_probe_ip(key, new_ip)
                host = new_ip

            # Per-probe interval override from config, falling back to the
            # live global default derived above
            interval_ms = default_interval_ms
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
            if not host:
                continue

            target_url = f"{base}/api/ingest"
            desired = (base, interval_ms, resolution_bits, self.token)
            # Once we've provisioned this probe this session, only
            # re-provision when its visible config (server_url /
            # interval) differs — this avoids the ESP32 doing an
            # NVS write (slow, brief stall) every cycle when nothing
            # has changed. Until then, always push so the current
            # token reaches it (the status shortcut can't see the
            # token; see _provisioned in __init__).
            if key in self._provisioned:
                # If the desired config is exactly what we last pushed
                # successfully, the probe is already up to date — skip
                # even the /status verification GET.
                if self._pushed.get(key) == desired:
                    continue
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
                    self._pushed[key] = desired
            except Exception as e:
                # best-effort; we'll retry next cycle
                log.warning("Failed to provision %s:%s: %s", host, port, e)
