# Support

_Last updated: 2026_

> **Note for the maker/reseller:** Setpoint is a white-label product. Before you
> ship, replace **Setpoint**/**Setpoint** with your product names and swap the
> placeholder support contacts below for your real ones. The support URL must
> match the `support_url` you set in your `branding` config
> (`https://example.com/support`).

Need a hand? We are happy to help you get your temperature monitoring running.

## How to reach us

- **Support site:** https://example.com/support
- **Email:** support@example.com
- **Hours:** we typically reply within one to two business days.

Please have your **order number / proof of purchase** and your **probe ID**
(for example `Setpoint-9A3F2C`) ready — it speeds things up a lot.

## Before you contact us: check the manual

Most questions are answered in the **[User Manual](docs/USER_MANUAL.md)** and the
project **README**. Common topics:

- **Starting the hub** — `Start.bat` (Windows) or `./Start.sh` (Linux); the
  dashboard opens at `http://localhost:8080`.
- **A probe won't appear** — confirm it is powered and joined to your Wi-Fi via
  its setup portal (the `Setpoint-<hex>` Wi-Fi network at
  `http://192.168.4.1`), and allow the hub through your firewall on **Private**
  networks so probes can reach it.
- **Readings look wrong** — check the probe's calibration (offset/gain) against a
  known reference such as an ice bath. Power-on `85.0` or disconnected `-127`
  values mean the sensor isn't reading; re-seat the DS18B20 and its pull-up.
- **No alerts** — alerts are off by default; enable notifications and set your
  SMTP or webhook details and a recipient.
- **Getting your data** — download `temperature_log.csv` from the dashboard.

## Quick self-check for a probe

Each probe answers a few local URLs on your network (port 80) that help diagnose
issues — for example `http://setpoint-<hex>.local/status` shows Wi-Fi signal,
uptime, the server it posts to, the last post result, and the current reading.
Sharing that output with us is very helpful.

## Reporting a bug

Found a software bug? Report it through **https://example.com/support** (or, if
you have the source, open an issue on the project's repository). A good report
lets us reproduce the problem fast.

**Please include:**

- **What happened** vs. **what you expected**, and how often it happens.
- **Steps to reproduce** — exactly what you did leading up to it.
- **Version info:** hub software version and protocol (from
  `http://localhost:8080/api/health`), and probe firmware version (`fw`, shown in
  the probe's `/whoami` or `/status`).
- **Your setup:** OS (Windows/Linux) and version, number of probes, sensor type
  (DS18B20 or MAX31855).
- **Probe ID(s)** involved, for example `Setpoint-9A3F2C`.
- **Health snapshot:** the JSON from `http://localhost:8080/api/health`
  (`rows_written`, `ingest_rejected`, `write_failures`, `last_write_age_sec`,
  `healthy`) — this tells us a lot at a glance.
- **Probe status:** the JSON from the probe's `/status` endpoint.
- **Screenshots or error text**, and any relevant lines from the hub's console
  window.

Please **do not** include secrets: your device token, SMTP password, or the
contents of `config.local.json`.

## Hardware issues, warranty, and returns

- Faulty hardware within the warranty period: see the **Limited Hardware
  Warranty** (`docs/WARRANTY.md`).
- Want to return or exchange a recent purchase: see **Returns & Refunds**
  (`docs/RETURNS.md`).

## Your privacy

Setpoint is local-first: no cloud, no account, no telemetry. When you contact
support, you choose what to share — see `PRIVACY.md` for how your data is
handled.
