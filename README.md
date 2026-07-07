# ThermaHub

**Local-first temperature monitoring for your fridge, freezer, fermentation, server closet, or greenhouse — with no cloud, no account, and no telemetry.**

ThermaHub is a small appliance app that runs on your own Windows or Linux PC. Wireless **ThermaProbe** sensors send their readings to it over your home or office network, and you watch everything live in your web browser. Your data never leaves your computer. There is nothing to sign up for and nothing phoning home.

---

## Why ThermaHub

- **Your data stays yours.** Readings are stored in a plain CSV file on your PC. No cloud service, no account, no tracking.
- **Plug and play.** Power a ThermaProbe on your Wi-Fi and it shows up automatically — the hub finds it and configures it for you.
- **Live dashboard.** A clean web page shows current temperature, charts, and rolling statistics for every probe.
- **Export anytime.** One click downloads a spreadsheet-ready CSV for Excel, Google Sheets, or your own analysis.
- **Calibrate & alert.** Trim each probe against a reference (ice bath) and get notified when a temperature goes out of range.
- **Secure by default.** The hub generates a private device token on first run and shares it only with your own probes over your local network.

---

## Quick start

1. **Start the hub.**
   - **Windows:** double-click **`Start.bat`**.
   - **Linux/macOS:** run **`./Start.sh`**.

   The first launch sets up its environment automatically (this takes a minute); later launches start instantly.

2. **Open the dashboard.** Your browser opens to **http://localhost:8080** on its own. If it doesn't, type that address in yourself. If Windows Firewall asks, click **Allow** on **Private** networks so probes can reach the hub.

3. **Connect a probe.** Power a ThermaProbe (USB adapter or battery) and follow the sticker on the unit to join it to your Wi-Fi. Within a few seconds the probe appears on the dashboard and readings begin. Full step-by-step instructions are in the **[User Manual](docs/USER_MANUAL.md)**.

4. **See readings.** Watch live temperature and charts update on the dashboard.

5. **Export CSV.** Click the download link to save `temperature_log.csv` for Excel or Sheets.

6. **Calibrate.** Trim a probe to a known reference with the one-point (ice-bath) procedure in the User Manual.

7. **Set alerts.** Choose a safe minimum/maximum for a probe and get notified when it drifts out of range.

> **New here?** The **[User Manual](docs/USER_MANUAL.md)** walks you through unboxing, joining Wi-Fi, reading data, calibrating, and troubleshooting — no technical background needed.

---

## For makers & developers

ThermaHub is a Python (Flask + Dash) app served by [waitress](https://pypi.org/project/waitress/) on port **8080**, plus open ESP32 firmware for the probes. If you want to build, extend, white-label, or self-assemble hardware:

- **[PROTOCOL.md](PROTOCOL.md)** — the hub⇄probe wire protocol (mDNS discovery, provisioning, ingest, probe HTTP endpoints).
- **[docs/DEVELOPING.md](docs/DEVELOPING.md)** — architecture, accurate file map, full REST API reference, config schema, environment variables, and how to run the tests.
- **[firmware/](firmware/)** — ESP32 probe firmware (PlatformIO project) and the factory-flash tooling.
- **[docs/BOM.md](docs/BOM.md)** — bill of materials for building your own probe hardware. See also **[docs/ASSEMBLY.md](docs/ASSEMBLY.md)**.
- **[docs/GO_TO_MARKET.md](docs/GO_TO_MARKET.md)** — market research and a go-to-market plan (niches, positioning, pricing, channels) for selling this at small scale.
- **[docs/COMPLIANCE.md](docs/COMPLIANCE.md)** — certification path (FCC/CE), calibration tiers, and which business segments you can realistically sell into.

### Homelab / self-hosted

ThermaHub drops into an existing self-hosted stack:

- **Prometheus** — scrape `http://<hub>:8080/metrics` (per-probe temperature + health counters) straight into Grafana.
- **Home Assistant / MQTT** — enable the `mqtt` block in config and each probe appears automatically as a temperature sensor (MQTT auto-discovery).
- **Docker** — `docker compose up -d` runs the hub headless with a persistent `./data` volume (see `docker-compose.yml`; use host networking for mDNS discovery).

---

## What's in this repo

| Path | What it is |
|---|---|
| `Start.bat` / `Start.sh` | One-click launchers (Windows / Linux-macOS). |
| `app.py` | Application entry point: builds the Dash UI, registers the API, starts discovery and auto-provisioning, serves on port 8080. |
| `api/routes.py` | REST API blueprint (`/api/...`). |
| `core/` | Config, storage/CSV, logging, mDNS advertising, notifications, paths, version. |
| `components/` | Dash dashboard UI pieces. |
| `probe_discovery.py` | Zeroconf browser that finds probes on the LAN. |
| `auto_provisioner.py` / `auto_provision.py` | Background provisioner / single-probe provision helper. |
| `config.example.json` | Shipped defaults; copied to `config.json` on first run. |
| `firmware/` | ESP32 probe firmware and flashing tools. |
| `docs/` | User manual, developer docs, BOM, assembly, and more. |
| `PROTOCOL.md` | Hub⇄probe protocol specification. |
| `temperature_log.csv` | Your live data log (created on first run; not in version control). |

> **Note:** Earlier versions of this README referenced files and a port (`8088`) that no longer match the app. The hub runs on **8080** and the layout above reflects what actually ships.

---

## License

See [LICENSE](LICENSE), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), and [docs/EULA.md](docs/EULA.md).
