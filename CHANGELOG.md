# Changelog

All notable changes to ThermaHub (the PC-side hub application) and its ThermaProbe
ESP32 firmware are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security
- **Ingest now bounds `probe_id`** — sanitized to `[A-Za-z0-9_-]`, capped at 32
  chars, before it reaches the database, CSV export, or an MQTT topic. A real
  ThermaProbe (`ThermaProbe-<HEX6>`) is unaffected; a buggy/malicious LAN client
  can no longer store an arbitrary value. (Guard restored after the v2.4.0 merge.)
- **CSV export is formula-injection-safe** — a cell beginning with `= + - @`
  (or tab/CR) is prefixed with a single quote so a spreadsheet treats it as text,
  not a formula. Defence-in-depth for the free-form export columns.

## [2.4.0] - 2026-07-11

The reconciled "ready to sell" release. It unifies two lines of development: the
SQLite data layer, battery firmware, diagnostics, alert-reliability and packaging
work, and the homelab integrations, humidity/VPD grow variant, tamper-evident audit
trail, optional dashboard login, and the go-to-market / compliance / manufacturing
documentation suite.

### Added
- **Alert hysteresis / deadband** (`alert_hysteresis_c`, default 0.5 °C). Once a
  probe is in breach it must move back *inside* its limit by this margin before the
  alert clears, so a noisy sensor sitting on a threshold no longer flaps
  high → recovery → high and spam-notifies. Entering a breach still uses the raw
  threshold; set it to 0 for the previous behaviour. Pure, unit-tested logic in
  `core.alerts`.
- **Battery / deep-sleep firmware mode.** The ThermaProbe can run in a low-power
  **deep-sleep** cycle for long life on a rechargeable lithium battery, in addition
  to the always-on (USB) mode. Probes **NTP-sync** their clock and **buffer readings
  offline**, flushing the queue to the hub on reconnect so a brief hub outage or
  Wi-Fi drop loses no data.
- **Prometheus `/metrics` endpoint** — per-probe temperature (plus humidity/VPD)
  gauges and health counters, for scraping into Grafana. Toggle via `metrics.enabled`.
- **MQTT publishing with Home Assistant auto-discovery** — optional `mqtt` config
  block, off by default; each probe appears automatically as a Home Assistant sensor.
- **Humidity + VPD support (grow variant)** — an optional `-D SENSOR_SHT4x` firmware
  build reads an SHT4x temperature+humidity sensor over I2C and adds an optional
  `humidity_pct` field to ingest (backward-compatible, still protocol v1). The hub
  computes **VPD** (vapour pressure deficit) via the Tetens formula with an optional
  `settings.vpd_leaf_offset_c` leaf offset, shows Humidity + VPD on the dashboard,
  exposes `thermahub_probe_humidity_percent` / `thermahub_probe_vpd_kpa` Prometheus
  gauges, publishes separate humidity/VPD MQTT/Home Assistant sensors, and evaluates
  `humidity_min/max` and `vpd_min/max` per-probe thresholds.
- **Docker / headless deployment** — `Dockerfile`, `docker-compose.yml`, and a
  `CONFIG_FILE` env override so the hub runs on a NAS/server with a persistent volume.
- **Optional dashboard login** — HTTP Basic auth on the dashboard + CSV download for
  shared office/lab LANs (`ui_auth` config or `UI_USERNAME`/`UI_PASSWORD`), off by
  default; `/api/*`, `/metrics`, and the operational endpoints are exempt.
- **Tamper-evident audit trail** — a hash-chained, append-only log of config changes
  and data exports (`logs/audit.log`), with an integrity check at
  `GET /api/audit/verify`. A B2B/procurement differentiator and a foundation for any
  future regulated (Part 11 / Annex 11) path.
- **Go-to-market, compliance & manufacturing documentation suite** under `docs/`:
  `GO_TO_MARKET.md`, `COMPLIANCE.md` (FCC/CE path, calibration tiers, sellable B2B
  segments), `LAUNCH.md`, `LISTING.md`, `BOM.md`, `ASSEMBLY.md`, `QC_CHECKLIST.md`,
  `LABEL_TEMPLATE.md`, `USER_MANUAL.md`, `EULA.md`, `WARRANTY.md`, and `RETURNS.md`,
  plus developer docs `CONTRIBUTING.md` and `TESTING.md`.

### Changed
- **Store listing** (`docs/LISTING.md`) rewritten as a ready-to-paste,
  homelab/server-room-first listing for the lead product (always-on USB DS18B20
  probe): honest spec table (accuracy vs resolution), can't-be-bricked/local
  positioning, homelab-stack integrations, photo shot list, and FAQ — reviewed
  against the compliance honesty rules.

### Fixed
- **Alert threshold of 0 was silently ignored on the dashboard.** The dashboard alert
  banner used a truthiness check (`if min_threshold`), so a valid `min: 0`
  (freezer/greenhouse) never triggered the banner — even though the server-side
  notifier (which uses `is not None`) still emailed/webhooked it. A single shared
  `threshold_breach()` helper now backs both the dashboard and the notifier so they
  can't diverge again; unit-tested including the 0-bound case.

### Security
- **Recursive secret redaction from `GET /api/config`.** Nested secrets — including
  the notification **webhook URL** (a bearer secret) and `smtp_password` — are now
  redacted, and the webhook URL is no longer seeded into the Settings page. The
  dashboard is open by default, so any LAN device could otherwise read them.
- **Firmware: per-unit unique, WPA2-protected setup AP.** The deep-sleep firmware's
  setup network was previously **open and shared one SSID** across all units. Each unit
  now brings up a unique setup AP (SSID == its probe id) protected by a **per-unit 64-bit
  random** WPA2 key, generated once at first boot and stored in NVS (printed on the serial
  `[label]` line for the factory tool). `firmware/factory_flash.py` captures the id + key
  from serial for the unit label. *(Needs a real Arduino build + flash + bench validation.)*
- **Firmware: probe identity rebranded to `ThermaProbe-<HEX6>`** (6 hex, sensor-ROM-derived
  with a MAC fallback, persisted in NVS) so a manufacturing batch won't collide.
- Security review of the release: hub core auth verified sound (no injection, auth
  bypass, path traversal, or unsafe deserialization).
- Expanded `SECURITY.md` into the merged threat model + hardening roadmap (token-gated
  mutating endpoints, recursive redaction, `ui_auth`, audit trail, the unauthenticated
  operational endpoints, and the open setup-AP and default-open `/provision` firmware
  items).

## [2.3.0] - Professional polish: diagnostics, onboarding & robustness

### Added
- **Diagnostics page** (top nav) and a secret-free `GET /api/diagnostics` endpoint:
  hub version, LAN URL, readings stored, database size, newest reading, retention,
  per-probe online/offline, and which notification channels are enabled — with a
  one-click **copy** for support. Channels report on/off only; hosts, URLs, passwords,
  and tokens are never included.
- **First-run onboarding.** The dashboard shows a step-by-step "waiting for your first
  reading…" card until data arrives, then hides itself; the Devices empty state now
  guides setup instead of a bare "no probes" message.
- **Live footer status** reflecting real hub state (N probes online / offline / idle /
  "waiting for first probe") instead of a hardcoded "Status: Ready", driven by pure,
  tested `core.status.hub_status`.
- **Config validation** (`core/config_schema.py`): a hand-edited or partial
  `config.json` is coerced to safe types/ranges on load, with each correction logged —
  a bad file can no longer crash the hub.
- Repo hygiene: `CONTRIBUTING.md`, `SECURITY.md`, GitHub issue/PR templates, and README
  status badges.
- A rewritten **Help** modal organised around what customers do (get online, name &
  calibrate, alerts, data & backup, troubleshooting) instead of an API endpoint list.

### Changed
- All service/UI `print()` calls now use the logging framework (`hub.<area>` loggers).
  In the packaged no-console build, `print()` output was lost — crash diagnostics now
  reach the rotating log file.

## [2.2.1] - Stable probe identity (no more duplicate cards)

### Fixed
- **A single probe could appear twice on the Devices page.** The firmware derived the
  probe id from the DS18B20 ROM code when that read succeeded (`TempProbe-XXXX`) but
  fell back to the ESP32 chip id when it failed on a cold boot (`TempSensor-XXXX`).
  Because the probe re-runs `setup()` on every deep-sleep wake, one physical device
  could report two identities and show as two cards (same IP). Fixed on both ends:
  - **Firmware (root cause, requires reflash):** the probe id is now derived once —
    retrying the ROM read so the first id is the good ROM-based one — then persisted to
    NVS and reused on every boot, so a later failed read can never flip the identity.
    Firmware bumped to **v1.6.0**.
  - **Hub (defensive, no reflash needed):** `list_probes()` now collapses entries that
    share a LAN IP to the single most recently-seen one, so a device shows as one card
    and is counted once in `/api/health`. Pure, unit-tested logic
    (`probe_discovery.dedupe_probes_by_ip`).

## [2.2.0] - Offline-probe alerts & standalone packaging

### Added
- **Offline / back-online notifications.** The alert monitor now flags a probe that
  stops reporting for longer than `offline_after_sec` (default 5 min) and notifies
  again when it resumes — essential for unattended monitoring, where a dead probe is as
  bad as an out-of-range one. Pure, unit-tested logic (`core/alerts.evaluate_offline`).
- The first monitor cycle seeds connectivity state silently, so a hub restart never
  emits a burst of "offline" for probes that were already quiet.
- Settings → Notifications: "Alert when a probe goes offline" toggle and an
  "Offline after (minutes)" field.
- **Standalone packaging** (`packaging/`): a PyInstaller spec + build scripts produce a
  single executable so customers run the hub without installing Python, plus a systemd
  unit and Windows/macOS service instructions. The app is now frozen-aware —
  `config.json`, the database, and logs are written next to the executable (overridable
  with `DATA_DIR`), while bundled assets/config load from the packaged resources.

## [2.1.0] - Notifications, calibration, retention & backups

### Added
- **Threshold notifications** that run server-side on a background thread
  (`alert_monitor.py`), so alerts fire even when no browser is open. Channels:
  **email (SMTP)** and **webhook** (Slack-compatible `text` field + structured JSON for
  Zapier/IFTTT/custom). Per-probe min/max thresholds with a `default` fallback, a
  configurable reminder cooldown, and optional "back to normal" recovery notices. Alert
  logic is a pure, unit-tested state machine (`core/alerts.py`) that only emits on
  transitions/cooldowns — never one message per poll.
- **Per-probe calibration offset** (`calibration_offsets`), applied at ingest so the
  stored value is the corrected temperature (DS18B20s vary ~±0.5 °C). Editable from the
  Devices → Edit Probe modal.
- **Data retention** (`retention_days`): readings older than N days are purged
  automatically (hourly), keeping disk bounded. 0 = keep forever.
- **One-click database backup** (`/download/backup.db`) — a consistent SQLite snapshot.
- A **Settings UI** to configure notifications and retention without editing JSON, with
  a "Send test" button.
- Rotating file logging (`core/logging_setup.py`, `logs/hub.log`) replacing ad-hoc
  prints in the startup/serving path.

### Fixed
- `latest_per_probe` now breaks epoch ties by insertion id, so "latest" is
  deterministic when two readings land in the same second.

## [2.0.0] - 2026-07-06

First public release. 1.0 was never shipped — it was an internal prototype used to
prove out the DS18B20-over-Wi-Fi idea and is not documented here. 2.0.0 is a full
productization of that prototype into a local-first, no-cloud appliance a non-technical
customer can plug in and run, built on a proper SQLite data layer.

### Added
- **Branding / config system** — everything ships from `config.json` (seeded on first
  run from `config.example.json`): product/brand name, support URL, primary color, logo,
  copyright, default unit, and timezone, so the hub is white-labelable without touching
  code. `config.json` is no longer tracked in git.
- **Unified device token** — one token, auto-generated on first run and saved to
  `config.local.json` (or supplied via `SERVER_TOKEN`). It guards all mutating endpoints
  and is pushed to probes by the auto-provisioner, so plug-and-play still works while the
  API stays authenticated.
- **SQLite data layer** (`core/db.py`, WAL mode) as the system of record — see *Changed*
  for the migration — with one-time automatic import of a legacy `temperature_log.csv`,
  index-backed time-window queries, and CSV export honouring the selected range
  (`/download/temperature_log.csv?window=24h`).
- **Firmware (ThermaProbe)** — ESP32 firmware with stable identity, SoftAP +
  captive-portal Wi-Fi setup, mDNS advertisement, and `/provision`, `/whoami`, and
  `/status` HTTP endpoints. DS18B20 fault codes (85.0 power-on, -127/NaN disconnect) are
  rejected instead of logged as real readings.
- **Probe online/offline status** (`age_sec`, `online`) on `/api/probes` and
  `/api/health`.
- **Documentation** — customer-facing README/SUPPORT/PRIVACY plus maker docs: protocol
  spec, QC checklist, and label template.
- **Tests** — pytest suite (`tests/`) covering the API, ingest validation, and config,
  and GitHub Actions CI.

### Changed
- **Storage migrated from CSV to SQLite** (`core/db.py`). The CSV file was rewritten in
  full to add columns and read in full by the dashboard every few seconds, which caused
  blank-dashboard / corruption issues under concurrent access and did not scale. SQLite
  (WAL mode) gives safe concurrent reads while probes write, and time-window queries are
  now index-backed.
- The dashboard now queries **only the selected time window** instead of re-reading and
  re-sorting the entire history on every 5 s refresh. Large windows are downsampled for
  plotting while statistics stay exact.
- **Production server** — the app is now served by **waitress** (a production WSGI
  server) when available, on port **8088**, falling back to the Flask dev server
  otherwise.
- **Ingest hardening** — `POST /api/ingest` validates that temperatures are finite and
  within -60..150 °C and that `probe_id` matches `^[A-Za-z0-9_-]{1,32}$`;
  `GET /api/ingest` returns 405. CSV export uses a fixed
  `timestamp,temperature_c,temperature_f,probe_id` schema.
- Renamed `auto_provision.py` → `provisioning.py` and `auto_provisioner.py` →
  `provisioner.py` for clarity.
- "Connected Probes" now counts only probes seen within the online window; long-gone
  probes are pruned from the Devices list.

### Fixed
- `GET /api/config` no longer leaks `provision_token` (secret values are redacted), and
  API token comparison is now constant-time.
- Settings → Probe Setup Helper callbacks are now registered (previously dead), and the
  Wi-Fi SSID scan only runs when the Settings page is open (previously it ran every few
  seconds from app start).
- Timezone conversion handles ISO timestamps with fractional seconds + offset
  (previously the offset could be silently dropped without converting).
- `provision_device.sh` now defaults to the correct hub port (8088, was 8080).
- Removed dead modules (`core/logger.py`, `components/probe_panel.py`,
  `components/temp_graph.py`) and the broken navbar logo reference; footer/version no
  longer shows placeholder branding.

### Security
- All mutating endpoints require the device token.
- Config is redacted (secrets stripped) when returned from `GET /api/config`.
- No account, no cloud, no telemetry — readings never leave the customer's PC.

[2.4.0]: https://example.com/thermahub/releases/2.4.0
[2.3.0]: https://example.com/thermahub/releases/2.3.0
[2.2.1]: https://example.com/thermahub/releases/2.2.1
[2.2.0]: https://example.com/thermahub/releases/2.2.0
[2.1.0]: https://example.com/thermahub/releases/2.1.0
[2.0.0]: https://example.com/thermahub/releases/2.0.0
