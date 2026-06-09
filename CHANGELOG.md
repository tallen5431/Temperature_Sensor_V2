# Changelog

All notable changes to the Temperature Hub (the PC-side application) are
documented here. The ESP32 firmware is versioned separately (see
`esp32_temp_probe/esp32_temp_probe.ino`).

## [2.3.0] — Professional polish: diagnostics, onboarding & robustness

### Added
- **Diagnostics page** (top nav) and a secret-free `GET /api/diagnostics`
  endpoint: hub version, LAN URL, readings stored, database size, newest
  reading, retention, per-probe online/offline, and which notification channels
  are enabled — with a one-click **copy** for support. Notification channels
  report on/off only; hosts, URLs, passwords, and tokens are never included.
- **First-run onboarding.** The dashboard shows a step-by-step "waiting for your
  first reading…" card until data arrives, then hides itself; the Devices empty
  state now guides setup instead of a bare "no probes" message.
- **Live footer status** reflecting real hub state (N probes online / offline /
  idle / "waiting for first probe") instead of a hardcoded "Status: Ready",
  driven by pure, tested `core.status.hub_status`.
- **Config validation** (`core/config_schema.py`): a hand-edited or partial
  `config.json` is coerced to safe types/ranges on load, with each correction
  logged — a bad file can no longer crash the hub.
- Repo hygiene: `CONTRIBUTING.md`, `SECURITY.md`, GitHub issue/PR templates, and
  README status badges.
- A rewritten **Help** modal organised around what customers do (get online,
  name & calibrate, alerts, data & backup, troubleshooting) instead of an API
  endpoint list.

### Changed
- All service/UI `print()` calls now use the logging framework
  (`hub.<area>` loggers). In the packaged no-console build, `print()` output was
  lost — crash diagnostics now reach the rotating log file.

## [2.2.1] — Stable probe identity (no more duplicate cards)

### Fixed
- **A single probe could appear twice on the Devices page.** The firmware
  derived the probe id from the DS18B20 ROM code when that read succeeded
  (`TempProbe-XXXX`) but fell back to the ESP32 chip id when it failed on a cold
  boot (`TempSensor-XXXX`). Because the probe re-runs `setup()` on every
  deep-sleep wake, one physical device could report two identities and show as
  two cards (same IP). Fixed on both ends:
  - **Firmware (root cause, requires reflash):** the probe id is now derived
    once — retrying the ROM read so the first id is the good ROM-based one — then
    persisted to NVS and reused on every boot, so a later failed read can never
    flip the identity. Firmware bumped to **v1.6.0**.
  - **Hub (defensive, no reflash needed):** `list_probes()` now collapses
    entries that share a LAN IP to the single most recently-seen one, so a
    device shows as one card and is counted once in `/api/health`. Pure,
    unit-tested logic (`probe_discovery.dedupe_probes_by_ip`).

## [2.2.0] — Offline-probe alerts & standalone packaging

### Added
- **Offline / back-online notifications.** The alert monitor now flags a probe
  that stops reporting for longer than `offline_after_sec` (default 5 min) and
  notifies again when it resumes — essential for unattended monitoring, where a
  dead probe is as bad as an out-of-range one. Pure, unit-tested logic
  (`core/alerts.evaluate_offline`).
- The first monitor cycle seeds connectivity state silently, so a hub restart
  never emits a burst of "offline" for probes that were already quiet.
- Settings → Notifications: "Alert when a probe goes offline" toggle and an
  "Offline after (minutes)" field.
- **Standalone packaging** (`packaging/`): a PyInstaller spec + build scripts
  produce a single executable so customers run the hub without installing
  Python, plus a systemd unit and Windows/macOS service instructions. The app is
  now frozen-aware — `config.json`, the database, and logs are written next to
  the executable (overridable with `DATA_DIR`), while bundled assets/config load
  from the packaged resources.

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
