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

2. **Probe SoftAP password is derived from the MAC (firmware).** The setup Wi-Fi SSID
   (`ThermaProbe-<hex>`) reveals the last 3 MAC bytes, and the WPA2 password is derived from the
   last 4 — so the setup-network key has low effective entropy and a captured handshake is
   crackable. During setup the probe transmits the user's home Wi-Fi credentials over plain HTTP on
   that network. **Recommended fix:** provision a full-entropy random AP password at flash time
   (printed on the unit label/QR) instead of deriving it from MAC bytes — see
   `firmware/factory_flash.py` and `deriveIdentity()` in `firmware/src/main.cpp`. **Interim
   mitigation:** the setup window is brief; perform first-time Wi-Fi setup away from untrusted RF.

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
