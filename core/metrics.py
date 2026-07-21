# core/metrics.py
"""Prometheus metrics for the #1 beachhead niche: homelab / self-hosted /
server-room monitoring.

Exposing a /metrics endpoint lets Setpoint drop straight into an existing
Prometheus + Grafana stack — the integration those buyers expect and that
cloud thermometers can't offer. Pure stdlib text exposition format; no deps.
"""
from __future__ import annotations

import threading
import time


class LatestReadings:
    """Thread-safe in-memory registry of the most recent reading per probe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, dict] = {}

    def record(self, probe_id: str, temp_c: float, ts_epoch: float | None = None,
               humidity: float | None = None, vpd: float | None = None) -> None:
        if not probe_id:
            return
        with self._lock:
            entry = {"temp_c": float(temp_c), "ts": ts_epoch or time.time()}
            if humidity is not None:
                entry["humidity"] = float(humidity)
            if vpd is not None:
                entry["vpd"] = float(vpd)
            self._data[probe_id] = entry

    def evict(self, probe_id: str) -> None:
        """Forget a probe's latest reading — call when a probe is removed so a
        decommissioned probe stops appearing as a frozen /metrics series (the
        dashboard/Devices/Diagnostics drop it immediately; this keeps Prometheus
        in step instead of serving its last temperature forever)."""
        if not probe_id:
            return
        with self._lock:
            self._data.pop(probe_id, None)

    def clear(self) -> None:
        """Forget every probe (used when clearing demo data)."""
        with self._lock:
            self._data.clear()

    def snapshot(self) -> dict[str, dict]:
        with self._lock:
            return {k: dict(v) for k, v in self._data.items()}


LATEST = LatestReadings()


def _esc_label(v: str) -> str:
    return str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def render_prometheus(health: dict, latest: dict, probes_count: int, version: str,
                      probes_online: int | None = None) -> str:
    """Render the Prometheus text exposition format for scraping.

    ``probes_online`` (when given) is the count of probes currently reporting
    within their freshness window — the same figure the dashboard shows as
    "Connected Probes" — so a Grafana alert on ``setpoint_probes_online`` agrees
    with the built-in UI instead of flapping for a deep-sleep probe.
    """
    lines: list[str] = []
    now = time.time()

    lines.append("# HELP setpoint_up Whether the hub process is serving (always 1 when scraped).")
    lines.append("# TYPE setpoint_up gauge")
    lines.append(f'setpoint_up{{version="{_esc_label(version)}"}} 1')

    lines.append("# HELP setpoint_probes_total Number of known probes.")
    lines.append("# TYPE setpoint_probes_total gauge")
    lines.append(f"setpoint_probes_total {int(probes_count)}")

    if probes_online is not None:
        lines.append("# HELP setpoint_probes_online Probes reporting within their freshness "
                     "window (matches the dashboard's Connected Probes).")
        lines.append("# TYPE setpoint_probes_online gauge")
        lines.append(f"setpoint_probes_online {int(probes_online)}")

    lines.append("# HELP setpoint_rows_written_total Readings written to the log since start.")
    lines.append("# TYPE setpoint_rows_written_total counter")
    lines.append(f"setpoint_rows_written_total {int(health.get('rows_written', 0))}")

    lines.append("# HELP setpoint_ingest_rejected_total Ingest requests rejected (bad/out-of-range).")
    lines.append("# TYPE setpoint_ingest_rejected_total counter")
    lines.append(f"setpoint_ingest_rejected_total {int(health.get('ingest_rejected', 0))}")

    lines.append("# HELP setpoint_write_failures_total CSV write failures since start.")
    lines.append("# TYPE setpoint_write_failures_total counter")
    lines.append(f"setpoint_write_failures_total {int(health.get('write_failures', 0))}")

    lines.append("# HELP setpoint_healthy Whether writes are flowing (1) or stale/failing (0).")
    lines.append("# TYPE setpoint_healthy gauge")
    lines.append(f"setpoint_healthy {1 if health.get('healthy') else 0}")

    lines.append("# HELP setpoint_probe_temperature_celsius Most recent temperature per probe.")
    lines.append("# TYPE setpoint_probe_temperature_celsius gauge")
    for pid, r in sorted(latest.items()):
        lines.append(f'setpoint_probe_temperature_celsius{{probe_id="{_esc_label(pid)}"}} {r["temp_c"]:.3f}')

    if any("humidity" in r for r in latest.values()):
        lines.append("# HELP setpoint_probe_humidity_percent Most recent relative humidity per probe.")
        lines.append("# TYPE setpoint_probe_humidity_percent gauge")
        for pid, r in sorted(latest.items()):
            if "humidity" in r:
                lines.append(f'setpoint_probe_humidity_percent{{probe_id="{_esc_label(pid)}"}} {r["humidity"]:.2f}')

    if any("vpd" in r for r in latest.values()):
        lines.append("# HELP setpoint_probe_vpd_kpa Most recent vapour pressure deficit per probe.")
        lines.append("# TYPE setpoint_probe_vpd_kpa gauge")
        for pid, r in sorted(latest.items()):
            if "vpd" in r:
                lines.append(f'setpoint_probe_vpd_kpa{{probe_id="{_esc_label(pid)}"}} {r["vpd"]:.3f}')

    lines.append("# HELP setpoint_probe_last_reading_age_seconds Seconds since a probe last reported.")
    lines.append("# TYPE setpoint_probe_last_reading_age_seconds gauge")
    for pid, r in sorted(latest.items()):
        age = max(0.0, now - float(r.get("ts", now)))
        lines.append(f'setpoint_probe_last_reading_age_seconds{{probe_id="{_esc_label(pid)}"}} {age:.1f}')

    return "\n".join(lines) + "\n"
