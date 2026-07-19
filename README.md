# Setpoint

[![CI](https://github.com/tallen5431/temperature_sensor_v2/actions/workflows/ci.yml/badge.svg)](https://github.com/tallen5431/temperature_sensor_v2/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![Hub](https://img.shields.io/badge/hub-v2.4.0-brightgreen)
![Firmware](https://img.shields.io/badge/firmware-v2.4.0-brightgreen)

**Local-first temperature (and humidity) monitoring for your fridge, freezer, fermentation, server closet, or greenhouse — with no cloud, no account, and no telemetry.**

Setpoint is a small appliance app that runs on your own Windows or Linux PC (or a NAS / Docker host). Wireless **Setpoint** sensors send their readings to it over your home or office network, and you watch everything live in your web browser. Data is stored in a local **SQLite** database on your machine and never leaves it — there is nothing to sign up for and nothing phoning home. Designed for **end users**: plug in the hub PC, power a probe, and data starts flowing with no manual setup.

---

## Why Setpoint

- **Your data stays yours.** Readings are kept in a local SQLite database (WAL mode) on your PC and are exportable to CSV — or as a full database snapshot — at any time. No cloud service, no account, no tracking.
- **Plug and play.** Power a Setpoint on your Wi-Fi and it shows up automatically — the hub discovers it over mDNS and provisions it for you.
- **Live dashboard.** A clean web page shows current temperature (plus humidity and VPD on grow probes), charts, and rolling statistics for every probe.
- **Export anytime.** One click downloads a spreadsheet-ready CSV, or a consistent SQLite snapshot for backup.
- **Calibrate & alert.** Trim each probe against a reference (ice bath) and get server-side notifications when a temperature drifts out of range — including when a probe goes silent.
- **Secure by default.** The hub generates a private device token on first run and shares it only with your own probes over your local network.
- **Homelab-friendly.** Prometheus `/metrics`, MQTT + Home Assistant auto-discovery, and headless Docker deployment drop into an existing self-hosted stack.

---

## Prerequisites

| Requirement | Minimum version | Download |
|---|---|---|
| **Python** | 3.9 | https://python.org/downloads |

> **Windows users:** During the Python installer tick **"Add Python to PATH"**, then click Install Now.

No other software is required. All Python packages are installed automatically on first run. If you would rather not install Python at all, Setpoint also ships as a **single executable** — see [Shipping a no-Python build](#shipping-a-no-python-build).

---

## Quick Start

### Windows

1. Double-click **`Start.bat`**
2. If Windows Firewall prompts, click **Allow** → **Private networks**
3. Your browser opens automatically at `http://localhost:8088`
4. Power the Setpoint via USB — readings appear within ~20 seconds

### macOS / Linux

```bash
# First run only — make the script executable:
chmod +x Start.sh

./Start.sh
```

Your browser opens automatically at `http://localhost:8088`.
If it does not open, navigate there manually.

> **Linux note:** If you see a firewall prompt or readings do not arrive, allow UDP port 5353 (mDNS) and TCP port 8088 for the hub process.

### Connect a probe

Power a Setpoint (USB adapter or rechargeable battery). On first use the probe broadcasts a **`Setpoint-XXXXXX`** Wi-Fi setup network — join it, then follow the captive-portal page (or the sticker on the unit) to hand it your home Wi-Fi credentials. Within a few seconds the probe appears on the dashboard and readings begin. Full step-by-step instructions are in the **[User Manual](docs/USER_MANUAL.md)** — no technical background needed.

> **Bare ESP32 board?** Flash the firmware straight from Chrome/Edge — no toolchain — with the browser-based installer in **[`flash/`](flash/)** (ESP Web Tools). It's the lowest-friction way for a maker/hobbyist to bring their own hardware online.

> Battery probes run in a **deep-sleep** low-power mode for long battery life; USB-powered probes run always-on. Either way the probe NTS-syncs its clock and buffers readings locally if the hub is briefly unreachable, flushing them on reconnect.

---

## How It Works

```
Probe (ESP32) ──mDNS──► Hub Discovery ──► Auto-Provisioner ──/provision──► Probe
Probe ──HTTP POST /api/ingest──► Hub API ──► temperature_log.db (SQLite)
                                   └──────► Live dashboard ──► CSV / backup export
```

1. **Discovery** — the hub listens for probes advertising `_temps-probe._tcp` via mDNS (Bonjour / Zeroconf) and itself advertises as `temps-hub.local`.
2. **Auto-Provisioner** — the hub automatically tells each probe where to POST readings (`http://<hub-ip>:8088/api/ingest`). No manual configuration on the probe is needed.
3. **Ingest** — the probe POSTs JSON every few seconds (temperature, and optionally `humidity_pct` on grow probes); the hub stores it in `temperature_log.db` and updates the dashboard. Use the dashboard's **Download CSV** button (or `/download/temperature_log.csv`, optionally `?window=24h`) to export, or `/download/backup.db` for a full snapshot.

> **Upgrading from a CSV-based version?** On first start the hub automatically imports any existing `temperature_log.csv` into the database — no data is lost. The CSV is then unused (SQLite is the system of record), but exporting to CSV stays a one-click operation.

---

## Configuration (optional)

All settings have sensible defaults. You can override them with environment variables before running the script, or edit them directly inside `Start.bat` / `Start.sh`.

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `8088` | HTTP port for the UI and API |
| `HOST` | `0.0.0.0` | Bind address (keep as-is for LAN access) |
| `PUBLIC_BASE` | auto-detected `http://<LAN-IP>:<PORT>` | URL the hub shares with probes |
| `SERVER_TOKEN` | auto-generated | Device token guarding every API write (ingest, provision, config). Auto-generated on first run and saved to `config.json`; set this to pin your own. The auto-provisioner pushes it to probes automatically as the `X-Token` header. |
| `DB_FILE` | `temperature_log.db` | Path to the SQLite data store |
| `CSV_FILE` | `temperature_log.csv` | Legacy CSV imported once on first start, then unused |
| `MDNS_ENABLE` | `1` | Set to `0` to disable hub mDNS advertisement |

Per-probe options (friendly names, alert thresholds, read interval, calibration offset) live in `config.json`, which is seeded from `config.example.json` on first run and is **not** tracked in git. The hub's UI **Settings** and **Devices** pages edit these for you.

> **Security:** every mutating endpoint is already token-gated (the token is auto-generated on first run), so probes and tools must hold the secret to post readings or change configuration. The **read-only dashboard**, however, is open on the LAN by default. On a shared office/lab network, enable **`ui_auth`** (HTTP Basic login) — see [SECURITY.md](SECURITY.md). Never port-forward the hub to the public internet.

---

## Notifications & Alerts

Set a **min/max threshold** per probe on the **Devices** page (✏️ Edit), then turn on
notifications under **Settings → Notifications**. A background monitor checks the
latest reading from each probe and notifies you when one goes out of range — it
runs server-side, so alerts fire even with no browser open.

| Channel | What you need |
|---|---|
| **Email** | SMTP host/port, username/password, from + to addresses. Port 465 uses SSL; 587 uses STARTTLS. |
| **Webhook** | A URL. The hub POSTs JSON with a Slack-compatible `text` field, so Slack/Discord/Zapier/IFTTT and custom relays (e.g. Twilio for SMS) all work. |

You also control a **reminder interval** (how often to re-notify while a probe stays
out of range), an **alert deadband / hysteresis** (°C — a probe must move back inside its
limit by this much before the alert clears, so a noisy sensor sitting on the threshold
doesn't flap; default 0.5), and whether to send a **"back to normal"** message on recovery.
Use **Send test** to verify your settings. Thresholds are in °C.

**Offline alerts:** the hub also notifies you when a probe **stops reporting** for
longer than *Offline after* (default 5 minutes), and again when it comes back —
so a dead or unplugged probe doesn't go unnoticed. Toggle it under
Settings → Notifications.

**Calibration:** if a probe reads slightly high or low, enter a **Calibration Offset (°C)**
in its Edit dialog — it's added to every reading at ingest, so stored data and alerts
are corrected.

**Data retention & backup (Settings → Data Management):** keep readings for a fixed
number of days (`retention_days`, 0 = keep forever), and download a one-click SQLite
**backup** (`/download/backup.db`) of the whole database.

---

## Humidity & VPD (grow variant)

The hub computes **VPD** (Vapour Pressure Deficit) from any probe that reports a
`humidity_pct` field alongside temperature (backward-compatible, still protocol v1): it
stores humidity + VPD, shows them on the dashboard, and exposes them in `/metrics` and over
MQTT / Home Assistant. Plain temperature-only probes are unaffected — those columns stay empty.

> **Firmware status:** an **SHT4x** temperature+humidity probe build is a planned variant and
> is **not yet in the shipping firmware** (`esp32_temp_probe.ino` is DS18B20-only). Humidity/VPD
> *alert thresholds* are likewise not wired yet — alerting is temperature-only for now. The
> hub-side plumbing above is live and ready for a humidity-reporting probe.

---

## Homelab / self-hosted

Setpoint drops into an existing self-hosted stack:

- **Prometheus** — scrape `http://<hub>:8088/metrics` (per-probe temperature / humidity / VPD gauges plus health counters) straight into Grafana. Toggle via `metrics.enabled`.
- **Home Assistant / MQTT** — enable the optional `mqtt` config block (off by default) and each probe appears automatically as a Home Assistant sensor (MQTT auto-discovery).
- **Docker** — `docker compose up -d` runs the hub headless with a persistent `./data` volume (see `Dockerfile` / `docker-compose.yml`; use host networking for mDNS discovery).

---

## File Map

| File | Purpose |
|---|---|
| `app.py` | Entry point — bootstraps Flask/Dash, runs under waitress, starts discovery, provisioner, and alert monitor |
| `api/routes.py` | REST endpoints: `/health`, `/config`, `/probes`, `/provision`, `/ingest` (calibration applied here), `/metrics`, `/diagnostics`, `/audit/verify` |
| `probe_discovery.py` | mDNS browser that finds and tracks probes (de-duplicates a probe seen under two identities) |
| `provisioning.py` / `provisioner.py` | Push ingest URL to probes (client functions / background thread) |
| `alert_monitor.py` | Background thread: threshold alerts + data-retention maintenance |
| `core/db.py` | SQLite reading store (WAL), windowed queries, CSV export, backup, retention, legacy-CSV import |
| `core/alerts.py` | Pure threshold/alert state machine (transitions, deadband, offline, recovery) |
| `core/notifications.py` | Email + webhook channels and the dispatcher |
| `core/config.py` / `core/config_schema.py` | Thread-safe JSON config + validation/normalisation on load |
| `core/storage.py` | Ingest payload normalisation and timezone handling |
| `core/status.py` / `core/diagnostics.py` | Live hub status (footer) and the diagnostics snapshot |
| `core/logging_setup.py` | Rotating file + console logging |
| `core/mdns_advert.py` | Advertises the hub on mDNS |
| `core/version.py` | Hub version / product metadata |
| `components/` | Dash UI panels (dashboard, devices, settings, diagnostics, probe setup wizard) |
| `config.example.json` | Default config seeded to `config.json` on first run |
| `Dockerfile` / `docker-compose.yml` | Headless deployment on a NAS/server with a persistent volume |
| `esp32_temp_probe/` | ESP32 Setpoint firmware — the deep-sleep/battery Arduino sketch (`esp32_temp_probe.ino`) |
| `firmware/` | Firmware contract (`src/protocol.h`), factory-flash/QC tooling, and firmware README |
| `packaging/` | PyInstaller spec + build scripts and service install for the no-Python build |
| `temperature_log.db` | SQLite data store (created automatically) |
| `tests/` | Pytest suite (data layer, API, alerts, notifications, monitor, dashboard, config, status, diagnostics, discovery) |

---

## API Quick Test

```bash
# Ingest a test reading (no probe needed)
curl -X POST -H 'Content-Type: application/json' -d '{"temperature_c":22.3}' http://localhost:8088/api/ingest"
# → {"ok": true}
```

Or open the URL directly in your browser — a new row should appear in the database and on the dashboard.

**Self-service support:** the **Diagnostics** page (top nav) shows hub version,
data store, probe status, retention, and notification health in one place, with
a one-click **copy** to paste into a bug report. The same secret-free snapshot is
available at `/api/diagnostics`.

**Audit trail:** every config change and data export is recorded in a
tamper-evident, hash-chained log (`logs/audit.log`); verify its integrity at
`GET /api/audit/verify`.

---

## For Developers

```bash
# Create an environment and install runtime + test dependencies
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

# Run the test suite
pytest
```

The hub runs under **waitress** (a production WSGI server) when it's installed,
and falls back to Flask's development server otherwise. Tests cover the SQLite
data layer, REST API, ingest/timezone normalisation, alerts/notifications, and the
dashboard computation. CI runs the same suite on every push (`.github/workflows/ci.yml`).

See **[TESTING.md](TESTING.md)** for the full test plan — automated suite,
hardware-in-the-loop, resilience/failure injection, notification checks, soak/load,
and a pre-release checklist. Contributing guidelines are in
**[CONTRIBUTING.md](CONTRIBUTING.md)**; security/deployment notes in
**[SECURITY.md](SECURITY.md)**. The ESP32 Setpoint firmware is the Arduino
sketch in `esp32_temp_probe/`; `firmware/` holds the firmware contract
(`src/protocol.h`) and the factory-flash/QC tooling.

### Shipping a no-Python build

To package the hub as a **single executable** customers can run without
installing Python (plus auto-start service setup for Linux/Windows/macOS), see
**[packaging/README.md](packaging/README.md)**: `./packaging/build.sh` (or
`packaging\build.bat` on Windows) produces `dist/temperature-hub/`.

---

## Selling & manufacturing

Building small batches to sell? The `docs/` suite covers the whole path from
prototype to product:

- **[docs/LAUNCH.md](docs/LAUNCH.md)** — step-by-step runbook to start selling small batches (validate → clear FCC → first batch → scale).
- **[docs/GO_TO_MARKET.md](docs/GO_TO_MARKET.md)** — market research, niches, positioning, pricing, and channels.
- **[docs/COMPLIANCE.md](docs/COMPLIANCE.md)** — certification path (FCC/CE), calibration tiers, and sellable B2B segments.
- **[docs/LISTING.md](docs/LISTING.md)** — a ready-to-paste online store listing (and **[docs/TINDIE_LISTING.md](docs/TINDIE_LISTING.md)** — the same, mapped onto Tindie's listing fields).
- **[docs/BOM.md](docs/BOM.md)** / **[docs/ASSEMBLY.md](docs/ASSEMBLY.md)** — bill of materials and build instructions for the probe hardware.
- **[docs/QC_CHECKLIST.md](docs/QC_CHECKLIST.md)** / **[docs/LABEL_TEMPLATE.md](docs/LABEL_TEMPLATE.md)** — per-unit quality control and the unit label template.
- **[docs/USER_MANUAL.md](docs/USER_MANUAL.md)** — customer-facing manual (unboxing, Wi-Fi, calibration, troubleshooting).
- **[docs/EULA.md](docs/EULA.md)**, **[docs/WARRANTY.md](docs/WARRANTY.md)**, **[docs/RETURNS.md](docs/RETURNS.md)** — legal / support paperwork.

---

## Licensing

Setpoint and its Setpoint firmware are **proprietary** — see
**[LICENSE](LICENSE)** (all rights reserved). They are built on open-source
components, each under its own license, catalogued in
**[THIRD-PARTY-LICENSES.md](THIRD-PARTY-LICENSES.md)** (regenerate with
`python packaging/gen_third_party_licenses.py`). Everything bundled is permissive
(MIT/BSD/Apache/MPL/PSF/ZPL) **except `zeroconf`** (hub) and `DallasTemperature` +
the ESP32 Arduino core (firmware), which are **LGPL-2.1**: you may ship a closed
product on top of them provided you carry the source offer in
`THIRD-PARTY-LICENSES.md` and keep the components replaceable (the packaged hub is
a PyInstaller *onedir* build, so they are).

> Before selling: replace the `[COPYRIGHT HOLDER]` / `[CONTACT EMAIL]` placeholders
> in `LICENSE`, and have an attorney review it and the end-user EULA (`docs/EULA.md`).
> This repo's files are a solid starting point, not legal advice.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| **Same probe shows twice** | Fixed in firmware **v1.6.0** + hub **v2.2.1** (the probe id is now stable across reboots and deep-sleep wakes). The hub also de-duplicates by IP, so older firmware no longer double-lists; reflash the probe to fix it at the source |
| **Probe appears in UI but no readings** | Wait ~20 s for auto-provisioner; or open `http://<probe-ip>/status` to verify its `server_url` |
| **401 Unauthorized on ingest** | Set `SERVER_TOKEN` env var and restart; the hub re-provisions probes with the token automatically |
| **No probes discovered** | A firewall may be blocking UDP 5353 (mDNS). Readings still work if the probe POSTs directly to the hub IP |
| **"Python not found" error** | Install Python 3.9+ from https://python.org/downloads and ensure it is on your PATH |
| **Port already in use** | Set `PORT=XXXX` before running, e.g. `PORT=9000 ./Start.sh` |
