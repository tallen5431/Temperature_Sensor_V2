# core/metrics.py
"""Prometheus metrics for the #1 beachhead niche: homelab / self-hosted /
server-room monitoring.

Exposing a /metrics endpoint lets ThermaHub drop straight into an existing
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

    def record(self, probe_id: str, temp_c: float, ts_epoch: float | None = None) -> None:
        if not probe_id:
            return
        with self._lock:
            self._data[probe_id] = {"temp_c": float(temp_c), "ts": ts_epoch or time.time()}

    def snapshot(self) -> dict[str, dict]:
        with self._lock:
            return {k: dict(v) for k, v in self._data.items()}


LATEST = LatestReadings()


def _esc_label(v: str) -> str:
    return str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def render_prometheus(health: dict, latest: dict, probes_count: int, version: str) -> str:
    """Render the Prometheus text exposition format for scraping."""
    lines: list[str] = []
    now = time.time()

    lines.append("# HELP thermahub_up Whether the hub process is serving (always 1 when scraped).")
    lines.append("# TYPE thermahub_up gauge")
    lines.append(f'thermahub_up{{version="{_esc_label(version)}"}} 1')

    lines.append("# HELP thermahub_probes_total Number of known probes.")
    lines.append("# TYPE thermahub_probes_total gauge")
    lines.append(f"thermahub_probes_total {int(probes_count)}")

    lines.append("# HELP thermahub_rows_written_total Readings written to the log since start.")
    lines.append("# TYPE thermahub_rows_written_total counter")
    lines.append(f"thermahub_rows_written_total {int(health.get('rows_written', 0))}")

    lines.append("# HELP thermahub_ingest_rejected_total Ingest requests rejected (bad/out-of-range).")
    lines.append("# TYPE thermahub_ingest_rejected_total counter")
    lines.append(f"thermahub_ingest_rejected_total {int(health.get('ingest_rejected', 0))}")

    lines.append("# HELP thermahub_write_failures_total CSV write failures since start.")
    lines.append("# TYPE thermahub_write_failures_total counter")
    lines.append(f"thermahub_write_failures_total {int(health.get('write_failures', 0))}")

    lines.append("# HELP thermahub_healthy Whether writes are flowing (1) or stale/failing (0).")
    lines.append("# TYPE thermahub_healthy gauge")
    lines.append(f"thermahub_healthy {1 if health.get('healthy') else 0}")

    lines.append("# HELP thermahub_probe_temperature_celsius Most recent temperature per probe.")
    lines.append("# TYPE thermahub_probe_temperature_celsius gauge")
    for pid, r in sorted(latest.items()):
        lines.append(f'thermahub_probe_temperature_celsius{{probe_id="{_esc_label(pid)}"}} {r["temp_c"]:.3f}')

    lines.append("# HELP thermahub_probe_last_reading_age_seconds Seconds since a probe last reported.")
    lines.append("# TYPE thermahub_probe_last_reading_age_seconds gauge")
    for pid, r in sorted(latest.items()):
        age = max(0.0, now - float(r.get("ts", now)))
        lines.append(f'thermahub_probe_last_reading_age_seconds{{probe_id="{_esc_label(pid)}"}} {age:.1f}')

    return "\n".join(lines) + "\n"
