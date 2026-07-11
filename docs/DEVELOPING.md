# Developing ThermaHub

Developer reference for the ThermaHub hub application. For the buyer-facing overview see the [root README](../README.md); for the wire protocol see [PROTOCOL.md](../PROTOCOL.md); for the probe firmware see [firmware/](../firmware/).

- **Product:** ThermaHub, version **2.4.0**, protocol **v1**.
- **Stack:** Python, Flask + [Dash](https://dash.plotly.com/) UI, served by [waitress](https://pypi.org/project/waitress/) on port **8088**.
- **Positioning:** local-first, no-cloud temperature-monitoring appliance. Readings stay on the customer's PC.

---

## Running from source

```bash
# Windows
Start.bat
# Linux / macOS
./Start.sh
```

Both launchers create a `.venv` and install `requirements.txt` on first run, then execute `app.py`. To run directly during development:

```bash
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
python app.py
```

On first run the app seeds `config.json` from `config.example.json`, creates the `temperature_log.db` SQLite database (WAL mode) — auto-importing a legacy `temperature_log.csv` once if one is present — and generates a device token (saved to `config.local.json`) unless one is supplied via `SERVER_TOKEN` or already present in config. The startup banner prints the local and LAN dashboard URLs.

---

## Architecture

```
ThermaProbe (ESP32) ──mDNS advertise──▶ ProbeDiscovery (zeroconf browse)
                                                 │
                                                 ▼
                                        AutoProvisioner (every 10s)
                                                 │  POST /provision {server_url, token, interval_ms}
                                                 ▼
ThermaProbe ──POST /api/ingest {temperature_c, probe_id, timestamp}──▶ Hub API
   headers: X-Probe-ID, X-Token                                          │
                                          ┌──────────────────────────────┤
                                          ▼                              ▼
                             validate + calibrate + append        NOTIFIER (thresholds)
                                          │                              │
                                          ▼                              ▼
                                temperature_log.db               email / webhook
                                          │
                                          ▼
                                   Dash dashboard (charts, stats)
```

- **`app.py`** boots logging, config, storage, discovery, the Flask server + API blueprint, the Dash app, mDNS advertising, and the auto-provisioner, then serves via waitress.
- **Device token** is resolved once at startup (`SERVER_TOKEN` env → config `provision_token` → freshly generated). The *same* token guards mutating API endpoints **and** is pushed to probes by the provisioner, so probes echo it back as `X-Token` and plug-and-play stays secure by default. An empty token means "open" (used only in tests / air-gapped dev).
- **Discovery** (`probe_discovery.py`) browses `_temps-probe._tcp.local.` and tracks last-seen probes.
- **Auto-provisioner** (`auto_provisioner.py`) periodically pushes the hub's ingest base URL + token + interval to every discovered probe by IP.
- **Storage** (`core/storage.py`) validates, calibrates, and appends readings under a process-wide write lock with an advisory OS file lock; it also escapes spreadsheet-formula fields and rejects out-of-range / non-finite values.

---

## File map

| Path | Responsibility |
|---|---|
| `app.py` | Entry point; wiring of UI, API, discovery, provisioner, mDNS, waitress. |
| `api/routes.py` | `create_api()` → Flask blueprint with all `/api/*` endpoints and auth. |
| `auto_provision.py` | `provision_probe()` — provision a single probe (POST its `/provision`). |
| `auto_provisioner.py` | `AutoProvisioner` background thread — provisions all discovered probes on a period. |
| `probe_discovery.py` | `ProbeDiscovery` — zeroconf browser; `list_probes()`, `update_last_seen()`. |
| `wifi_scan.py` | Wi-Fi scan helper used by setup UI. |
| `provision_device.sh` | Shell helper to provision a probe manually. |
| `core/config.py` | `Config` — loads `config.json`, coerces values via `config_schema`, persists, and audits changes. |
| `core/config_schema.py` | `normalize_config` — validates/repairs a hand-edited config without crashing the hub. |
| `core/storage.py` | Ingest payload normalization + timezone handling; humidity/VPD helpers (`compute_vpd`, `extract_humidity`) and the shared `threshold_breach`. |
| `core/db.py` | `Database` — the SQLite (WAL) readings store (system of record): schema, windowed reads/downsampling, retention purge, CSV import/export, backup. |
| `core/alerts.py` / `alert_monitor.py` | Threshold + offline alert evaluation (hysteresis) and the background `AlertMonitor` thread (also runs the retention purge). |
| `core/notifications.py` | `Notifier` — sends alert events over email/webhook with a cooldown. |
| `core/metrics.py` | Prometheus `/metrics` exposition + the in-memory `LATEST` per-probe registry. |
| `core/mqtt_publish.py` | Optional MQTT publishing + Home Assistant auto-discovery (`MQTT`). |
| `core/audit.py` | Tamper-evident hash-chained audit log (`AUDIT`), verified at `/api/audit/verify`. |
| `core/diagnostics.py` / `core/status.py` | Secret-free health snapshot for `/api/diagnostics` + the Diagnostics view. |
| `core/applog.py` | `get_logger` + the `HEALTH` counters surfaced on `/api/health` and `/metrics`. |
| `core/logging_setup.py` | Rotating-file + console logging configuration. |
| `core/mdns_advert.py` | `MdnsAdvert` — advertises the hub over mDNS. |
| `core/version.py` | `HUB_VERSION`/`__version__` (2.4.0), `PRODUCT_NAME`, `PROTOCOL_VERSION` (1). |
| `components/layout_main.py` | Builds the Dash layout, page routing, callback registration. |
| `components/*.py` | Dashboard UI pieces (dashboard, devices, settings, diagnostics, help, probe-setup wizard). |
| `config.example.json` | Shipped default config; copied to `config.json` on first run. |
| `tests/` | Pytest suite (data layer, API/auth, alerts, notifications, monitor, dashboard, metrics, MQTT, audit, config, status, diagnostics, discovery). |
| `firmware/` | Firmware contract (`src/protocol.h`) + factory-flash / QC tooling (`factory_flash.py`). The ESP32 ThermaProbe firmware itself is the Arduino sketch `esp32_temp_probe/esp32_temp_probe.ino` (deep-sleep/battery), built with the Arduino toolchain / arduino-cli. |
| `temperature_log.db` | Live readings database — SQLite (WAL), git-ignored. |

---

## REST API reference

All endpoints are under the `/api` prefix. Mutating endpoints require the device token, supplied as the `X-Token` header, a `token` query parameter, or a `token` field in a JSON body. When the resolved token is empty (tests / dev), auth is open. Unauthorized requests return `401 {"ok": false, "error": "unauthorized"}`.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/health` | no | Liveness + health snapshot (see fields below). |
| GET | `/api/config` | yes | Redacted config as JSON (all secrets removed). |
| POST | `/api/config` | yes | Update config values and persist; returns redacted config. |
| GET | `/api/probes` | no | List discovered probes. |
| POST | `/api/provision` | yes | Hub pushes ingest URL + token to probe(s). |
| POST | `/api/ingest` | yes | Ingest one reading. |
| GET | `/api/ingest` | — | Always `405` (POST only; prevents drive-by log poisoning). |
| POST | `/api/ingest_csv` | yes | Bulk ingest of CSV lines (max 1000 rows/request). |

Additionally, two files are downloadable outside `/api` (served by Flask): `GET /download/temperature_log.csv` **exports** readings as CSV (optionally `?window=24h`), and `GET /download/backup.db` returns a full SQLite snapshot. Any other path returns 404.

### `GET /api/health`

Returns:

```json
{
  "ok": true,
  "version": "2.4.0",
  "protocol": 1,
  "probes": 2,
  "base": "http://192.168.1.50:8088",
  "time": "2026-07-06T10:00:00",
  "rows_written": 1234,
  "ingest_rejected": 3,
  "write_failures": 0,
  "last_write_age_sec": 4.2,
  "healthy": true
}
```

- `probes` — count of currently discovered probes.
- `base` — the public base URL the hub advertises to probes.
- `rows_written`, `ingest_rejected`, `write_failures` — cumulative counters.
- `last_write_age_sec` — seconds since the last successful database write (`null` if none yet).
- `healthy` — `true` only if there has been a recent write (< 120 s) and no write failures.

### `POST /api/ingest`

- Body: `{ "temperature_c": <float> }` or `{ "temperature_f": <float> }`, plus optional `probe_id` and `timestamp`. (Aliases `temp_c/t_c/c` and `temp_f/t_f/f` are also accepted.)
- Headers: `X-Probe-ID` (should equal the mDNS TXT `id` and body `probe_id`; a mismatch is logged, not fatal) and `X-Token`.
- Validation: temperature must be finite and within **-60..150 °C**; `probe_id` must match `^[A-Za-z0-9_-]{1,32}$` (invalid IDs become empty). Bodies over 64 KiB return `413`.
- Calibration (`gain` then `offset_c`) is applied per probe before logging, and Fahrenheit is recomputed from the calibrated Celsius.
- Returns `{"ok": true}` on success; `400` on missing/out-of-range value; `500` on write failure.

### `POST /api/provision`

Body `{ host?, port?, interval_ms?, token? }`. With no `host`, the hub provisions every discovered probe by IP. Returns `{ ok, provided_to[], failed[], total, success_count, server_base }`.

---

## Config schema

Config is layered: `config.json` (seeded from `config.example.json`) with `config.local.json` overrides. Secrets are redacted from API responses.

| Key | Type / notes |
|---|---|
| `interval_sec` | Probe post interval in seconds (default 5). |
| `auto_provision` | Enable the background provisioner (default true). |
| `pull_enabled` | Enable pull-mode behavior. |
| `provision_token` | The device token (usually generated; do not commit `config.local.json`). |
| `branding` | `{ product_name, brand_name, support_url, primary_color, copyright, logo_path }` — white-labeling. |
| `settings` | `{ default_unit, timezone }`. |
| `notifications` | `{ enabled, recipients[], webhook_url, debounce_sec, smtp_host, smtp_port, smtp_user, smtp_password, smtp_from, smtp_tls }`. |
| `calibration` | `{ <probe_id>: { offset_c, gain } }` (a `default` entry applies to unlisted probes). |
| `alert_thresholds` | `{ default: { min, max } }` (per-probe entries override the default). |
| `probe_names` | `{ <probe_id>: <friendly name> }`. |

The CSV **export** columns are fixed: `timestamp,temperature_c,temperature_f,probe_id,humidity_pct,vpd_kpa`.

---

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `HOST` | `0.0.0.0` | Bind address for the server. |
| `PORT` | `8088` | HTTP port for UI + API. |
| `PUBLIC_BASE` | `http://<detected-LAN-IP>:<PORT>` | Base URL advertised to probes; set to override auto-detection. |
| `SERVER_TOKEN` | *(empty → generated)* | Forces the device token; takes precedence over config. |
| `UI_USERNAME` / `UI_PASSWORD` | *(unset)* | Enable HTTP Basic auth on the dashboard + CSV download (also configurable via the `ui_auth` config block). |
| `DB_FILE` | `<data>/temperature_log.db` | Path to the SQLite readings database. |
| `CSV_FILE` | `<repo>/temperature_log.csv` | Legacy CSV auto-imported once on first run (if present). |
| `CONFIG_FILE` | `<repo>/config.json` | Path to the runtime config (override for Docker volumes). |
| `LOG_DIR` | `<repo>/logs` | Directory for application logs. |
| `MDNS_ENABLE` | `1` | Set to `0`/`false` to disable the hub's mDNS advertising. |

---

## Homelab / self-hosted integrations

**Prometheus** — `GET /metrics` exposes the exposition format for scraping (per-probe
`thermahub_probe_temperature_celsius`, plus health counters). Enabled by default; disable with
`metrics.enabled: false` in config. It is unauthenticated by design (scrape it on a trusted LAN).

**MQTT + Home Assistant auto-discovery** — off by default. Enable the `mqtt` block in config
(`enabled`, `host`, `port`, `username`, `password`, `base_topic`, `discovery_prefix`,
`discovery_enabled`). Each reading is published to `<base_topic>/<probe_id>/state`, and (once per
probe) a retained HA discovery config to `<discovery_prefix>/sensor/thermahub_<probe_id>/config`,
so probes appear automatically as temperature sensors in Home Assistant. Requires `paho-mqtt`
(in `requirements.txt`); a missing package degrades to a warning.

**Docker** — `docker compose up -d` runs the hub with a persistent `./data` volume. mDNS
auto-discovery needs the host network (`network_mode: host`, the default in `docker-compose.yml`);
on Docker Desktop, use the bridge override and point probes at the host's LAN IP.

**Dashboard login** — off by default (single-user home setups stay frictionless). Set
`ui_auth.enabled` + `username`/`password` in config, or `UI_USERNAME`/`UI_PASSWORD` env, to require
HTTP Basic auth on the dashboard and CSV download for a shared office/lab LAN. `/api/*` (device-token
auth) and `/metrics` (Prometheus scrape) are intentionally exempt.

**Audit trail** — config changes and CSV exports are recorded to a hash-chained, append-only
`logs/audit.log` (each entry hashes the previous one, so silent edits break the chain — only key
names are logged, never secret values). `GET /api/audit/verify` (auth) reports chain integrity and
entry count. See `docs/COMPLIANCE.md` for how this fits a B2B / regulated path.

**Log retention** — a background task (`core/retention.py`) keeps the readings database bounded for 24/7 use:
readings newer than `retention.raw_days` are kept full-resolution, older ones are thinned to one per
probe per `downsample_interval_min`, and anything past `downsample_days` is dropped. Runs hourly +
shortly after startup, atomically under the write lock. Set `retention.enabled: false` to keep
everything (and manage disk yourself).

---

## Running tests

```bash
pip install -r requirements-dev.txt
pytest            # from the repo root
pytest -q tests/test_api_routes.py   # a single file
```

The suite covers the API routes, config layering, storage/validation, and probe discovery. Tests run with an empty (open) token where applicable.
