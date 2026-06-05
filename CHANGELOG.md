# Changelog

All notable changes to the Temperature Hub (the PC-side application) are
documented here. The ESP32 firmware is versioned separately (see
`esp32_temp_probe/esp32_temp_probe.ino`).

## [2.1.0] — Notifications, calibration, retention & backups

### Added
- **Threshold notifications** that run server-side on a background thread
  (`alert_monitor.py`), so alerts fire even when no browser is open. Channels:
  **email (SMTP)** and **webhook** (Slack-compatible `text` field +
  structured JSON for Zapier/IFTTT/custom). Per-probe min/max thresholds with a
  `default` fallback, a configurable reminder cooldown, and optional
  "back to normal" recovery notices. Alert logic is a pure, unit-tested state
  machine (`core/alerts.py`) that only emits on transitions/cooldowns — never
  one message per poll.
- **Per-probe calibration offset** (`calibration_offsets`), applied at ingest so
  the stored value is the corrected temperature (DS18B20s vary ~±0.5 °C).
  Editable from the Devices → Edit Probe modal.
- **Data retention** (`retention_days`): readings older than N days are purged
  automatically (hourly), keeping disk bounded. 0 = keep forever.
- **One-click database backup** (`/download/backup.db`) — a consistent SQLite
  snapshot.
- A **Settings UI** to configure notifications and retention without editing
  JSON, with a "Send test" button.
- Rotating file logging (`core/logging_setup.py`, `logs/hub.log`) replacing ad-hoc
  prints in the startup/serving path.

### Fixed
- `latest_per_probe` now breaks epoch ties by insertion id, so "latest" is
  deterministic when two readings land in the same second.

## [2.0.0] — Hub data layer & production hardening

### Changed
- **Storage migrated from CSV to SQLite** (`core/db.py`). The CSV file was
  rewritten in full to add columns and read in full by the dashboard every few
  seconds, which caused blank-dashboard / corruption issues under concurrent
  access and did not scale. SQLite (WAL mode) gives safe concurrent reads while
  probes write, and time-window queries are now index-backed.
- The dashboard now queries **only the selected time window** instead of
  re-reading and re-sorting the entire history on every 5 s refresh. Large
  windows are downsampled for plotting while statistics stay exact.
- The hub now serves under **waitress** (a production WSGI server) when
  available, falling back to the Flask dev server otherwise.
- Renamed `auto_provision.py` → `provisioning.py` and `auto_provisioner.py` →
  `provisioner.py` for clarity.
- "Connected Probes" now counts only probes seen within the online window;
  long-gone probes are pruned from the Devices list.

### Added
- One-time automatic import of a legacy `temperature_log.csv` into the database.
- CSV export honours the selected time range (`/download/temperature_log.csv?window=24h`).
- Probe online/offline status (`age_sec`, `online`) on `/api/probes` and `/api/health`.
- `config.example.json` is seeded to `config.json` on first run; `config.json`
  is no longer tracked in git.
- Test suite (`tests/`) and GitHub Actions CI.

### Fixed
- `GET /api/config` no longer leaks `provision_token` (secret values are redacted).
- API token comparison is now constant-time.
- Settings → Probe Setup Helper callbacks are now registered (previously dead),
  and the Wi-Fi SSID scan only runs when the Settings page is open (previously
  it ran every few seconds from app start).
- Timezone conversion handles ISO timestamps with fractional seconds + offset
  (previously the offset could be silently dropped without converting).
- `provision_device.sh` now defaults to the correct hub port (8088, was 8080).
- Removed dead modules (`core/logger.py`, `components/probe_panel.py`,
  `components/temp_graph.py`) and the broken navbar logo reference.
- Footer/version no longer shows placeholder branding.
