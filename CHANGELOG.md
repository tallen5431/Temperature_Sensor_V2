# Changelog

All notable changes to TempSensor (the PC-side hub application) and its TempSensor
ESP32 firmware are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Smarter CSV export.** "Download CSV" now exports exactly what you're viewing — the selected time
  range and, in focus mode, just that probe. A new **Export** dialog adds a custom **date range** and
  **per-probe** selection. Backed by `Database.export_csv(probe_id=…, start_epoch=…, end_epoch=…)` and
  `?probe=`/`?from=`/`?to=` query params on the download route.
- **Unambiguous timestamps in exports.** Every CSV row now carries a `timestamp_utc` column derived
  from the reading's epoch, alongside the existing local `timestamp`, so exported data stays correct
  across daylight-saving changes and different machines. The export dialog names the hub's timezone.
- **System health panel (Diagnostics).** An at-a-glance health card — status (Healthy / Needs
  attention), uptime, readings in the last 24 h, last write, rows written this run, rejected ingests,
  write failures, and free disk — with a low-disk warning. So you can trust the logger is recording.
- **Try it with demo data.** The first-run empty state has a **▶ Load demo data** button that seeds a
  day of realistic sample readings (clearly-labelled `Demo …` probes) so a new user can explore the
  dashboard, charts, export and per-probe views before any hardware arrives; a banner offers one-click
  **Clear demo data**, which never touches real probes.
- **Remove a device.** The Devices edit dialog now has a **🗑 Remove device** button (with a
  confirmation) that deletes all of a probe's readings and its saved name / thresholds / calibration /
  interval, and forgets it from discovery — so accumulated test devices can be cleared. New
  `Database.delete_probe()` and `ProbeDiscovery.forget_probe()`. A still-powered probe will reappear on
  its next reading (the dialog says so) — power it off first to remove it for good.
- **Dashboard focus mode.** A "🔍 Viewing" selector lets you drill from the all-probes overview into a
  single probe: the gauge, history graph and Min/Avg/Max statistics then show only that probe (with its
  own threshold band and auto-ranged axis), and the per-probe overview grids collapse to just that one.
  A many-probe hub can now be read either at a glance or one probe at a time, instead of an
  ever-growing wall of cards. New `Database.window_stats(probe_id=…)`; the graph palette grew to 12
  colours so more probes stay distinct.

### Changed
- **Settings page is clearer.** The alerts card is split into **When to alert** and **Where to send
  alerts**; the Email and Webhook fields stay collapsed until you enable that channel (progressive
  disclosure); the retention field shows a live "0 = keep everything, forever" / "⚠ older readings are
  permanently deleted" note and reads in plain-language sections; and there's a direct link to the
  Devices page where per-probe alert limits are actually set.
- **Form styling polish (Settings, edit dialogs).** Inputs and selects were bright white against the
  dark UI; they are now dark-themed to match, section headers are brightened with a divider line, and
  the hover "lift" is limited to the interactive probe cards instead of every card.

### Added
- **Per-probe Min / Avg / Max statistics** — when 2+ probes have data, the dashboard adds a per-probe
  statistics breakdown below the overall row, so a mixed deployment isn't collapsed into one
  meaningless aggregate (an "average" across a −18 °C freezer and a 22 °C room is nonsense). A
  single-probe deployment is unchanged — the global row already tells the whole story. Backed by a new
  `Database.stats_per_probe()` query.
- **Per-probe status cards on the dashboard** — one card per probe showing its current temperature and
  an at-a-glance **OK / HIGH / LOW / stale** state (colour-coded, with a freshness age), so a
  multi-probe deployment is legible at a glance instead of a single gauge showing whichever probe
  reported last.
- **The main gauge is now useful** — it focuses on the probe that needs attention (the worst active
  threshold breach, else the latest reading), draws **coloured threshold zones** (blue below min, green
  in the safe band, red above max), colours the bar by state, and auto-ranges the axis around the band
  — so a −18 °C freezer and a 32 °C office each read sensibly instead of on a fixed 0–100 scale.

### Changed
- **The Devices page now lists probes known only from ingest** (not just mDNS-discovered ones), so a
  **deep-sleep battery probe** — whose radio is off between readings and is never mDNS-visible — still
  appears and can be renamed / thresholded / calibrated.
- **Dashboard styling is now fully offline** — the Bootstrap/CYBORG theme is vendored locally
  (`assets/bootstrap-cyborg.min.css`) instead of loaded from a CDN, so the hub renders correctly with
  no internet (offline homelabs, air-gapped networks) — matching the local-first promise. Dash already
  serves its own JS/Plotly locally, so the hub now needs zero external hosts.
- **"Connected Probes" counts probes that are actually reporting** (from the readings DB within the
  online window), not just mDNS-discovered ones — so a **deep-sleep battery probe** (radio off between
  readings, never mDNS-visible) is correctly counted while it is posting.

### Fixed
- **Dashboard freshness no longer flickers deep-sleep probes offline.** The "Connected Probes" count and
  the per-probe **stale** badge used a fixed 60 s online window, so a battery probe that wakes every few
  minutes read as offline between wakes even while healthily reporting. The window is now the larger of
  the online timeout, the alert monitor's `offline_after_sec` (default 5 min — so the dashboard and the
  offline **alerts** now agree), and ~2.5× the probe's configured reporting interval. A typical
  deep-sleep probe now stays "connected" between wakes with no per-probe configuration.
- **Browser flasher now targets the ESP32-C3 we actually ship on.** `flash/manifest.json` declared
  `chipFamily: "ESP32"` (classic), so ESP Web Tools would **refuse to flash** a C3 board. It now
  declares **`ESP32-C3`**, `build_merged_bin.sh` compiles for the C3 with the **No-OTA (2MB APP / 2MB
  SPIFFS)** partition scheme and prefers the core's own chip-correct merged image, and the
  manual-flash / `factory_flash.py` FQBN defaults follow suit. (Browser flashing writes the whole
  image over USB serial, so the no-OTA scheme flashes fine — OTA only concerns wireless updates.)
- **Rebranded to `TempSensor`** — the hub, the probe, the firmware, the Prometheus metric prefix
  (`tempsensor_*`), the MQTT base topic, and all documentation now use **TempSensor** in place of
  ThermaHub/ThermaProbe. The probe's setup-AP SSID and probe ID become **`TempSensor-<HEX6>`**.
  **Probes must be reflashed** to pick up the new identity (they will report under a new ID after
  reflashing).
- **Setup Wi-Fi is now an open network** — the probe's first-time setup SoftAP (`TempSensor-<HEX6>`)
  no longer uses a WPA2 password, so setup is one-tap. The AP only exists during provisioning and is
  torn down once the probe joins the home Wi-Fi; the `[label]` serial line now prints `ap_pass=none`,
  and the label/QC docs drop the Wi-Fi-password field. A per-unit WPA2 key can be reintroduced for
  higher-security deployments (see `SECURITY.md`).

### Added
- **Browser-based firmware flashing** (`flash/`) — an [ESP Web Tools](https://esphome.github.io/esp-web-tools/)
  page that flashes the TempSensor firmware onto an ESP32-C3 from Chrome/Edge with no toolchain,
  plus `build_merged_bin.sh` to produce the merged image and a README for hosting it (GitHub
  Pages). The lowest-friction on-ramp for kit/BYO-hardware hobbyists. (Binary is generated, not
  committed; needs a hardware bench build.)
- **Hobbyist go-to-market ladder** in `docs/LAUNCH.md` — a lowest-barrier path (software/BYO →
  kits → assembled+SDoC → B2B), tied to the browser-flash on-ramp.
- **`docs/TINDIE_LISTING.md`** — a ready-to-paste Tindie listing (title, summary, tags, kit/assembled
  price options, Markdown description, shipping, photo order) with a pre-publish checklist covering
  Tindie's exclusivity clause and the FCC-for-assembled caveat.

### Changed
- `docs/LAUNCH.md`: noted Tindie's web-exclusivity (pick one paid channel for the probe) and pointed
  the kit/direct-sell steps at `TINDIE_LISTING.md`.
- Corrected the README **Humidity & VPD** section to the shipped reality: the hub computes VPD
  from any probe that reports humidity, but the SHT4x probe *firmware build* and humidity/VPD
  *alert thresholds* are not yet implemented (temperature-only alerting for now).
- `docs/LAUNCH.md`: the deep-sleep **battery** capability now ships in the firmware, so it's a
  packaging option rather than a future architecture change; refreshed the release checklist.

### Security
- **Ingest now bounds `probe_id`** — sanitized to `[A-Za-z0-9_-]`, capped at 32
  chars, before it reaches the database, CSV export, or an MQTT topic. A real
  TempSensor (`TempSensor-<HEX6>`) is unaffected; a buggy/malicious LAN client
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
- **Battery / deep-sleep firmware mode.** The TempSensor can run in a low-power
  **deep-sleep** cycle for long life on a rechargeable lithium battery, in addition
  to the always-on (USB) mode. Probes **NTS-sync** their clock and **buffer readings
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
  exposes `tempsensor_probe_humidity_percent` / `tempsensor_probe_vpd_kpa` Prometheus
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
- **Firmware: probe identity rebranded to `TempSensor-<HEX6>`** (6 hex, sensor-ROM-derived
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
- **Firmware (TempSensor)** — ESP32 firmware with stable identity, SoftAP +
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

[2.4.0]: https://example.com/tempsensor/releases/2.4.0
[2.3.0]: https://example.com/tempsensor/releases/2.3.0
[2.2.1]: https://example.com/tempsensor/releases/2.2.1
[2.2.0]: https://example.com/tempsensor/releases/2.2.0
[2.1.0]: https://example.com/tempsensor/releases/2.1.0
[2.0.0]: https://example.com/tempsensor/releases/2.0.0
