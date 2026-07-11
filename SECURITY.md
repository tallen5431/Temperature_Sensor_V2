# Security

ThermaHub is a **local-first, LAN-only** appliance: the hub runs on the customer's own PC and
talks only to probes on the local network. There is no cloud service and no internet exposure by
default. The threat model below assumes an attacker who is **another device/user on the same LAN**
(the hub is not meant to be port-forwarded to the internet — don't do that).

## What is protected

- **Device token** gates every mutating API endpoint (`/api/ingest`, `/api/provision`,
  `/api/config`, `/api/ingest_csv`, `/api/audit/verify`). It is auto-generated on first run and
  pushed to probes by the provisioner, so plug-and-play works without leaving the API open.
- **`/download` is restricted to the log file only** (exact-path check), resolved against the
  configured CSV location.
- **Secrets are redacted** from API responses (`provision_token`, any `password`, `webhook_url`,
  `smtp_password`) and are **never seeded into the Settings page** (rendered blank, kept on save).
- **Ingest is validated**: POST-only, finite/in-range temperatures, `probe_id` constrained to
  `^[A-Za-z0-9_-]{1,32}$`, spreadsheet formula-injection escaped, body size capped.
- **Tamper-evident audit trail** (`logs/audit.log`) hash-chains config changes and data exports.
- **Optional dashboard login** (`ui_auth`) adds HTTP Basic auth for shared office/lab LANs.

## Known limitations & hardening roadmap

These are deliberate trade-offs or items slated for the next firmware revision. They are LAN-local
and medium severity, but a maker shipping to customers should plan to address the firmware ones.

1. **Dashboard is open on the LAN by default.** The read-only dashboard (and `/metrics`) are
   reachable by any device on the network unless `ui_auth` is enabled. On a shared/office LAN,
   **turn on `ui_auth`** (config or `UI_USERNAME`/`UI_PASSWORD`). Recipient emails and SMTP host/user
   entered in Settings are visible to anyone who can open the dashboard — gate it with `ui_auth`.

2. **Probe SoftAP password (firmware) — FIXED, pending a hardware build test.** Earlier the WPA2
   setup-network key was derived from the MAC (which the SSID partly exposes), making a captured
   handshake crackable. The firmware now generates a **per-unit 64-bit random** password once at
   first boot, stores it in NVS, and prints it on the serial `[label]` line for the factory tool to
   put on the unit label (`ensureApPassword()` in `firmware/src/main.cpp`; captured by
   `firmware/factory_flash.py`). Note: the setup page still transmits the home Wi-Fi credentials over
   plain HTTP within that WPA2-protected SoftAP — acceptable given a strong random key, but do first
   setup away from untrusted RF. **Like all firmware changes here, this must be validated with a real
   PlatformIO build + flash + bench test before manufacturing.**

3. **Probe `/provision` is unauthenticated by default (firmware).** To keep zero-touch plug-and-play
   working, the probe accepts `/provision` (which sets its ingest `server_url`) without a secret
   unless one is stored. This means any LAN device can repoint a probe's readings. This is the same
   trust boundary as discovery itself (any LAN host can act as a hub). **To lock a unit down**, store
   a per-device provision secret (`X-Provision-Secret`, from the unit label/QR); the firmware then
   enforces it. Consider enabling this for units on untrusted networks.

4. **`/metrics`, `/api/probes`, `/api/health` are unauthenticated** (even when `ui_auth` is on).
   They expose probe IDs and temperatures (non-secret operational data) so Prometheus can scrape
   them. Don't expose the hub to untrusted networks.

## Reporting a vulnerability

Email the maintainer (replace with your address before publishing): `security@example.com`.
Please include the version (`GET /api/health` → `version`) and reproduction steps. We aim to
acknowledge within a few business days.
