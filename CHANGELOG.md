# Changelog

All notable changes to ThermaHub are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Refinements aimed at the homelab / self-hosted beachhead (see `docs/GO_TO_MARKET.md`).

### Added
- **Humidity + VPD support (grow variant)** — an optional `-D SENSOR_SHT4x` firmware
  build reads an SHT4x temperature+humidity sensor over I2C (GPIO21/22) and adds an
  optional `humidity_pct` field to ingest (backward-compatible, still protocol v1).
  The hub computes **VPD** (vapour pressure deficit) from temperature + humidity using
  the Tetens formula with an optional `settings.vpd_leaf_offset_c` leaf offset, adds
  `humidity_pct,vpd_kpa` CSV columns (old logs auto-upgraded), shows Humidity + VPD on
  the dashboard, exposes `thermahub_probe_humidity_percent` / `thermahub_probe_vpd_kpa`
  Prometheus gauges, publishes separate humidity and VPD MQTT/Home Assistant sensors,
  and evaluates `humidity_min/max` and `vpd_min/max` per-probe alert thresholds.
- **Prometheus `/metrics` endpoint** — per-probe temperature gauges plus health
  counters, for scraping into Grafana. Toggle via `metrics.enabled`.
- **MQTT publishing with Home Assistant auto-discovery** (optional, `mqtt` config
  block) — each probe appears automatically as a Home Assistant temperature sensor.
- **Docker / headless deployment** — `Dockerfile`, `docker-compose.yml`, and a
  `CONFIG_FILE` env override so the hub runs on a NAS/server with a persistent volume.
- **Optional dashboard login** — HTTP Basic auth on the dashboard + CSV download for
  shared office/lab LANs (`ui_auth` config or `UI_USERNAME`/`UI_PASSWORD`), off by
  default; `/api/*` and `/metrics` are exempt.
- **Tamper-evident audit trail** — a hash-chained, append-only log of config changes
  and data exports (`logs/audit.log`), with an integrity check at
  `GET /api/audit/verify`. A B2B/procurement differentiator and a foundation for any
  future regulated (Part 11 / Annex 11) path.
- **Go-to-market & compliance strategy** — `docs/GO_TO_MARKET.md` and
  `docs/COMPLIANCE.md` (certification path, calibration tiers, sellable B2B segments).

### Fixed
- **CSV download button** returned the dashboard HTML instead of the log after the
  absolute-path refactor (the link had a double slash that missed the download
  route). It now links by basename; regression-tested.

### Removed
- Dead modules: `core/logger.py` (unused `PullLogger`) and the orphaned
  `components/temp_graph.py` / `components/probe_panel.py`.

## [2.0.0] - 2026-07-06

First public release. 1.0 was never shipped — it was an internal prototype used
to prove out the DS18B20-over-Wi-Fi idea and is not documented here. 2.0.0 is a
full productization of that prototype into a local-first, no-cloud appliance a
non-technical customer can plug in and run.

### Added
- **Branding / config system** — everything ships from `config.json` (seeded on
  first run from `config.example.json`): product/brand name, support URL, primary
  color, logo, copyright, default unit, and timezone, so the hub is white-labelable
  without touching code.
- **Unified device token** — one token, auto-generated on first run and saved to
  `config.local.json` (or supplied via `SERVER_TOKEN`). It guards all mutating
  endpoints and is pushed to probes by the auto-provisioner, so plug-and-play
  still works while the API stays authenticated.
- **Calibration** — per-probe `offset_c` and `gain` applied to incoming readings.
- **Notifications** — threshold alerts over SMTP and/or webhook, with recipient
  list and debounce.
- **Firmware (ThermaProbe)** — ESP32 firmware with stable MAC-derived identity,
  SoftAP + captive-portal Wi-Fi setup, mDNS advertisement, and `/provision`,
  `/whoami`, and `/status` HTTP endpoints. DS18B20 fault codes (85.0 power-on,
  -127/NaN disconnect) are rejected instead of logged as real readings.
- **Documentation** — customer-facing README/SUPPORT/PRIVACY plus maker docs:
  protocol spec, QC checklist, and label template.
- **Tests** — pytest suite covering the API, ingest validation, and config.

### Changed
- **Production server** — the app is now served by **waitress** on port 8080
  instead of the Flask/Dash development server.
- **CSV integrity** — the temperature log is written with a fixed
  `timestamp,temperature_c,temperature_f,probe_id` schema, and
  `/download/temperature_log.csv` is the only downloadable file.
- **Ingest hardening** — `POST /api/ingest` validates that temperatures are
  finite and within -60..150 C and that `probe_id` matches
  `^[A-Za-z0-9_-]{1,32}$`; `GET /api/ingest` returns 405.

### Security
- All mutating endpoints require the device token.
- Config is redacted (secrets stripped) when returned from `GET /api/config`.
- No account, no cloud, no telemetry — readings never leave the customer's PC.

[2.0.0]: https://example.com/thermahub/releases/2.0.0
