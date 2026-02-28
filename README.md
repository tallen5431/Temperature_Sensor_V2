# Temperature Sensor Hub

Collects temperature readings from ESP32 probes over Wi-Fi, shows a live chart in your browser, and logs data to a CSV file. Designed for **end users**: plug in the hub PC, power the probe, and data starts flowing — no manual setup.

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
Probe ──HTTP POST /api/ingest──► Hub API ──► temperature_log.csv
                                   └──────► Live dashboard
```

1. **Discovery** — the hub listens for probes advertising `_temps-probe._tcp` via mDNS (Bonjour / Zeroconf).
2. **Auto-Provisioner** — the hub automatically tells each probe where to POST readings (`http://<hub-ip>:8088/api/ingest`). No manual configuration on the probe is needed.
3. **Ingest** — the probe POSTs JSON every few seconds; the hub appends to `temperature_log.csv` and updates the dashboard.

---

## Configuration (optional)

All settings have sensible defaults. You can override them with environment variables before running the script, or edit them directly inside `Start.bat` / `Start.sh`.

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `8088` | HTTP port for the UI and API |
| `HOST` | `0.0.0.0` | Bind address (keep as-is for LAN access) |
| `PUBLIC_BASE` | auto-detected `http://<LAN-IP>:<PORT>` | URL the hub shares with probes |
| `SERVER_TOKEN` | *(empty)* | Optional shared secret; probes must include it as `X-Token` |
| `CSV_FILE` | `temperature_log.csv` | Path to the data log |

The hub's UI also has a **Settings** page for common options (probe names, alert thresholds, auto-provision toggle).

---

## File Map

| File | Purpose |
|---|---|
| `app.py` | Entry point — bootstraps Flask/Dash, starts discovery and auto-provisioner |
| `api/routes.py` | REST endpoints: `/health`, `/config`, `/probes`, `/provision`, `/ingest` |
| `probe_discovery.py` | mDNS browser that finds and tracks probes |
| `auto_provision.py` / `auto_provisioner.py` | Push ingest URL to probes (single / background) |
| `core/config.py` | Thread-safe JSON config management |
| `core/storage.py` | CSV append and payload normalisation |
| `core/mdns_advert.py` | Advertises the hub on mDNS |
| `components/` | Dash UI panels (dashboard, devices, probe setup wizard) |
| `temperature_log.csv` | Live data log (created automatically) |

---

## API Quick Test

```bash
# Ingest a test reading (no probe needed)
curl "http://localhost:8088/api/ingest?temperature_c=22.3"
# → {"ok": true}
```

Or open the URL directly in your browser — a new row should appear in `temperature_log.csv` and on the dashboard.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| **Probe appears in UI but no readings** | Wait ~20 s for auto-provisioner; or open `http://<probe-ip>/status` to verify its `server_url` |
| **401 Unauthorized on ingest** | Set `SERVER_TOKEN` env var and restart; the hub re-provisions probes with the token automatically |
| **No probes discovered** | A firewall may be blocking UDP 5353 (mDNS). Readings still work if the probe POSTs directly to the hub IP |
| **"Python not found" error** | Install Python 3.9+ from https://python.org/downloads and ensure it is on your PATH |
| **Port already in use** | Set `PORT=XXXX` before running, e.g. `PORT=9000 ./Start.sh` |
