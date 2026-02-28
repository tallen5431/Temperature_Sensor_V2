# Temperature Sensor Hub — Product README

This hub app collects temperature readings from ESP32 probes (DS18B20 / thermocouple front-ends), shows live charts in a web UI, and logs data to CSV for Excel/analysis. It’s designed for **end users**: plug in the hub PC, power the probe, and data starts flowing—no manual setup.

---
## Highlights
- **Auto-discover probes** on your LAN using mDNS (Bonjour/Zeroconf).
- **Auto-provision probes** (no buttons, no curl): the hub tells each probe where to POST.
- **Live dashboard** (Dash/Flask) with rolling stats.
- **CSV logging** to `temperature_log.csv` for easy analysis.
- **Optional token auth** for secure ingest.

---
## Quick Start (Windows)
1. Double-click **`Start.bat`** (creates a venv, installs deps, and starts the hub).
2. If Windows Firewall prompts, click **Allow** for Python on **Private** networks.
3. Power the probe (ESP32) via USB. Within ~10–20 seconds, readings should appear.
4. Open the UI shown in the console, e.g. `http://192.168.1.145:8088`.
5. CSV grows in real time at **`temperature_log.csv`** in the project folder.

> If you see the probe in the UI but no data, give it ~10 seconds: the background **auto-provisioner** sets the probe’s `server_url` automatically.

---
## How It Works
```
Probe (ESP32) ──mDNS──▶ Hub Discovery ──▶ Auto-Provisioner ──/provision──▶ Probe
Probe ──HTTP POST /api/ingest──▶ Hub API ──▶ CSV (temperature_log.csv)
                                  └──────▶ UI charts
```
- **Discovery** finds probes advertising `_temps-probe._tcp`.
- **Auto-Provisioner** pushes the correct ingest URL (e.g., `http://<hub-ip>:8088/api/ingest`) to each probe **by IP** (no `.local` DNS).
- **Probe firmware** reads the sensor and POSTs JSON to the hub at the configured interval.

---
## Configuration (optional)
You can set these in environment variables (e.g., inside `Start.bat`).

| Variable | Default | Purpose |
|---|---|---|
| `HOST` | `0.0.0.0` | Bind address for the hub |
| `PORT` | `8088` | HTTP port for UI & API |
| `PUBLIC_BASE` | computed `http://<LAN-IP>:<PORT>` | Base URL the hub shares with probes |
| `SERVER_TOKEN` | *(empty)* | Shared secret; probes include it as `X-Token` on POST |
| `CSV_FILE` | `temperature_log.csv` | Where readings are stored |

**PUBLIC_BASE**: if not set, the hub auto-detects your LAN IP and uses `http://<lan-ip>:<port>`.

---
## File Map
- **`app.py`** — Bootstraps Flask/Dash, registers the API, starts discovery & auto-provisioner.
- **`api/routes.py`** — REST endpoints: health, config, probes, provision, and ingest.
- **`probe_discovery.py`** — Zeroconf browser that finds probes and normalizes info.
- **`auto_provision.py` / `auto_provisioner.py`** — Provision a probe (single / background all).
- **`core/mdns_advert.py`** — Advertises the hub on mDNS (Bonjour).
- **`components/`** — Dash UI parts (`probe_panel.py`, `temp_graph.py`, `setup_helper.py`).
- **`temperature_log.csv`** — Live data log.

---
## API Quick Test
Open a browser on the hub PC:
```
http://<hub-ip>:8088/api/ingest?temperature_c=22.3
```
You should get `{ "ok": true }` and a new row in the CSV.

---
## Troubleshooting
- **Probe in UI, no data**: wait ~10s for auto-provision; or open `http://<probe-ip>/status`.
- **401 Unauthorized**: set `SERVER_TOKEN` and restart; hub will re-provision token.
- **No discovery**: firewall may block UDP 5353; logging still works (IP-based provisioning).
