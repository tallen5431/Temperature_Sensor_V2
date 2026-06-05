# Temperature Sensor Hub

Collects temperature readings from ESP32 probes over Wi-Fi, shows a live chart in your browser, and logs data to a local SQLite database (exportable to CSV at any time). Designed for **end users**: plug in the hub PC, power the probe, and data starts flowing — no manual setup.

---

## Prerequisites

| Requirement | Minimum version | Download |
|---|---|---|
| **Python** | 3.9 | https://python.org/downloads |

> **Windows users:** During the Python installer tick **"Add Python to PATH"**, then click Install Now.

No other software is required. All Python packages are installed automatically on first run.

---

## Quick Start

### Windows

1. Double-click **`Start.bat`**
2. If Windows Firewall prompts, click **Allow** → **Private networks**
3. Your browser opens automatically at `http://localhost:8088`
4. Power the ESP32 probe via USB — readings appear within ~20 seconds

### macOS / Linux

```bash
# First run only — make the script executable:
chmod +x Start.sh

./Start.sh
```

Your browser opens automatically at `http://localhost:8088`.
If it does not open, navigate there manually.

> **Linux note:** If you see a firewall prompt or readings do not arrive, allow UDP port 5353 (mDNS) and TCP port 8088 for the hub process.

---

## How It Works

```
Probe (ESP32) ──mDNS──► Hub Discovery ──► Auto-Provisioner ──/provision──► Probe
Probe ──HTTP POST /api/ingest──► Hub API ──► temperature_log.db (SQLite)
                                   └──────► Live dashboard ──► CSV export
```

1. **Discovery** — the hub listens for probes advertising `_temps-probe._tcp` via mDNS (Bonjour / Zeroconf).
2. **Auto-Provisioner** — the hub automatically tells each probe where to POST readings (`http://<hub-ip>:8088/api/ingest`). No manual configuration on the probe is needed.
3. **Ingest** — the probe POSTs JSON every few seconds; the hub stores it in `temperature_log.db` and updates the dashboard. Use the dashboard's **Download CSV** button (or `/download/temperature_log.csv`) to export.

> **Upgrading from a CSV-based version?** On first start the hub automatically imports any existing `temperature_log.csv` into the database — no data is lost.

---

## Configuration (optional)

All settings have sensible defaults. You can override them with environment variables before running the script, or edit them directly inside `Start.bat` / `Start.sh`.

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `8088` | HTTP port for the UI and API |
| `HOST` | `0.0.0.0` | Bind address (keep as-is for LAN access) |
| `PUBLIC_BASE` | auto-detected `http://<LAN-IP>:<PORT>` | URL the hub shares with probes |
| `SERVER_TOKEN` | *(empty)* | Optional shared secret; when set, every API write (ingest, provision, config) must include it as the `X-Token` header. The auto-provisioner pushes it to probes automatically. |
| `DB_FILE` | `temperature_log.db` | Path to the SQLite data store |
| `CSV_FILE` | `temperature_log.csv` | Legacy CSV imported once on first start, then unused |
| `MDNS_ENABLE` | `1` | Set to `0` to disable hub mDNS advertisement |

Per-probe options (friendly names, alert thresholds, read interval, calibration offset) live in `config.json`, which is seeded from `config.example.json` on first run and is **not** tracked in git. The hub's UI **Settings** and **Devices** pages edit these for you.

> **Security:** the hub serves on your LAN with no authentication by default. For anything beyond a trusted home network, set `SERVER_TOKEN` so only probes (and tools) holding the secret can post readings or change configuration.

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
out of range) and whether to send a **"back to normal"** message on recovery. Use
**Send test** to verify your settings. Thresholds are in °C.

**Calibration:** if a probe reads slightly high or low, enter a **Calibration Offset (°C)**
in its Edit dialog — it's added to every reading at ingest, so stored data and alerts
are corrected.

**Data retention & backup (Settings → Data Management):** keep readings for a fixed
number of days (0 = forever), and download a one-click SQLite **backup** of the whole
database.

---

## File Map

| File | Purpose |
|---|---|
| `app.py` | Entry point — bootstraps Flask/Dash, runs under waitress, starts discovery, provisioner, and alert monitor |
| `api/routes.py` | REST endpoints: `/health`, `/config`, `/probes`, `/provision`, `/ingest` (calibration applied here) |
| `probe_discovery.py` | mDNS browser that finds and tracks probes |
| `provisioning.py` / `provisioner.py` | Push ingest URL to probes (client functions / background thread) |
| `alert_monitor.py` | Background thread: threshold alerts + data-retention maintenance |
| `core/db.py` | SQLite reading store (WAL), windowed queries, CSV export, backup, retention, legacy-CSV import |
| `core/alerts.py` | Pure threshold/alert state machine (transitions, cooldown, recovery) |
| `core/notifications.py` | Email + webhook channels and the dispatcher |
| `core/config.py` | Thread-safe JSON config management |
| `core/storage.py` | Ingest payload normalisation and timezone handling |
| `core/logging_setup.py` | Rotating file + console logging |
| `core/mdns_advert.py` | Advertises the hub on mDNS |
| `core/version.py` | Hub version / product metadata |
| `components/` | Dash UI panels (dashboard, devices, settings, probe setup wizard) |
| `config.example.json` | Default config seeded to `config.json` on first run |
| `temperature_log.db` | SQLite data store (created automatically) |
| `tests/` | Pytest suite (data layer, API, alerts, notifications, monitor, dashboard) |

---

## API Quick Test

```bash
# Ingest a test reading (no probe needed)
curl "http://localhost:8088/api/ingest?temperature_c=22.3"
# → {"ok": true}
```

Or open the URL directly in your browser — a new row should appear in the database and on the dashboard.

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
and a pre-release checklist.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| **Probe appears in UI but no readings** | Wait ~20 s for auto-provisioner; or open `http://<probe-ip>/status` to verify its `server_url` |
| **401 Unauthorized on ingest** | Set `SERVER_TOKEN` env var and restart; the hub re-provisions probes with the token automatically |
| **No probes discovered** | A firewall may be blocking UDP 5353 (mDNS). Readings still work if the probe POSTs directly to the hub IP |
| **"Python not found" error** | Install Python 3.9+ from https://python.org/downloads and ensure it is on your PATH |
| **Port already in use** | Set `PORT=XXXX` before running, e.g. `PORT=9000 ./Start.sh` |
