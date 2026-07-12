# Security

TempSensor is a **local-first, LAN-only** appliance: the hub runs on the customer's own PC and
talks only to probes on the local network. There is no cloud service and no internet exposure by
default. The threat model below assumes an attacker who is **another device/user on the same LAN**
(the hub is not meant to be port-forwarded to the internet — don't do that).

## What is protected

- **Device token** gates every mutating API endpoint (`POST /api/ingest`, `/api/provision`,
  `POST /api/config`, `/api/ingest_csv`). It is auto-generated on first run (saved to
  `config.json`, or pin your own via `SERVER_TOKEN`) and pushed to probes by the
  provisioner as the `X-Token` header, so plug-and-play works without leaving the API open.
  Token comparison is constant-time.
- **`/download` is restricted** to the log file and the database backup only (exact-path check),
  resolved against the configured data location.
- **Secrets are recursively redacted** from `GET /api/config` — nested values too (`provision_token`,
  any `password`, `smtp_password`, `webhook_url`) — and are **never seeded into the Settings page**
  (rendered blank, kept on save). `/api/diagnostics` reports notification channels as on/off only and
  never includes hosts, URLs, passwords, or tokens.
- **Ingest is validated**: POST-only (`GET /api/ingest` returns 405), finite/in-range temperatures,
  `probe_id` constrained to `^[A-Za-z0-9_-]{1,32}$`, spreadsheet formula-injection escaped, body
  size capped.
- **Tamper-evident audit trail** (`logs/audit.log`) hash-chains config changes and data exports;
  its integrity is verifiable at `GET /api/audit/verify`.
- **Optional dashboard login** (`ui_auth`) adds HTTP Basic auth to the dashboard and CSV download
  for shared office/lab LANs (config, or `UI_USERNAME`/`UI_PASSWORD`), off by default.

## Operational endpoints (unauthenticated by design)

`/metrics`, `/api/probes`, `/api/health`, and `/api/diagnostics` return non-secret **operational
data** (probe IDs, temperatures/humidity, online status, hub version, retention, channel on/off)
and stay open even when `ui_auth` is on, so Prometheus can scrape and support tools can read a
health snapshot. They expose no secrets, but don't reach the hub from untrusted networks.

## Known limitations & hardening roadmap

These are deliberate trade-offs or items slated for the next firmware revision. They are LAN-local
and medium severity, but a maker shipping to customers should plan to address the firmware ones.

1. **Dashboard is open on the LAN by default.** The read-only dashboard (and the operational
   endpoints above) are reachable by any device on the network unless `ui_auth` is enabled. On a
   shared/office LAN, **turn on `ui_auth`** (config or `UI_USERNAME`/`UI_PASSWORD`). Recipient emails
   and the SMTP host/user entered in Settings are visible to anyone who can open the dashboard —
   gate it with `ui_auth`.

2. **Probe setup SoftAP is open (firmware) — an intentional usability trade-off.** On first boot the
   probe brings up a **per-unit-unique but OPEN** setup network (SSID == the probe id) and serves the
   WiFiManager captive portal at `192.168.4.1`. It is open (no password) so setup is one-tap; the AP
   only exists during first-time provisioning and disappears once the probe joins the home Wi-Fi. The
   residual risk is narrow: during that one-time setup window the portal transmits the home Wi-Fi
   credentials over plain HTTP, so someone within RF range at that exact moment could observe them —
   do first setup away from untrusted RF. This is the same posture as most consumer IoT. **For a
   higher-security deployment**, the firmware can be built to bring up a **per-unit random WPA2** setup
   AP instead (printed on the `[label]` serial line for the unit label) — the code for this is in the
   project history; reintroduce it if you sell into an environment that requires it.

3. **Probe `/provision` is unauthenticated by default (firmware).** To keep zero-touch plug-and-play
   working, the probe accepts `/provision` (which sets its ingest `server_url`) without a secret
   unless one is stored. This means any LAN device can repoint a probe's readings. This is the same
   trust boundary as discovery itself (any LAN host can act as a hub). **To lock a unit down**, store
   a per-device provision secret (`X-Provision-Secret`, from the unit label/QR); the firmware then
   enforces it. Consider enabling this for units on untrusted networks. Note the probe's HTTP surface
   is small (`GET /`, `/whoami`, `/status`; `POST /provision`); Wi-Fi credentials are entered only
   through the WiFiManager captive portal, which runs during SoftAP setup, not in station mode.

## Deploying safely

- **Keep it on a trusted network.** Treat dashboard access as equivalent to LAN access. Do not
  port-forward the hub to the public internet.
- **Enable `ui_auth`** on any shared or multi-tenant LAN.
- **Pin `SERVER_TOKEN`** if you want a known token rather than the auto-generated one; the
  auto-provisioner distributes it to probes for you.
- **Secrets stay local.** Notification passwords, tokens, and webhook URLs live only in
  `config.json` next to the app, and are redacted from every API response.

## Reporting a vulnerability

Please report security issues privately rather than opening a public issue. Use GitHub's
**Report a vulnerability** (Security → Advisories) on this repository, or email the maintainer
(replace with your address before publishing): `security@example.com`. We aim to acknowledge within
a few business days and will keep you updated on a fix.

When reporting, include the hub version (see the **Diagnostics** page or `GET /api/diagnostics` /
`GET /api/health` → `version`), the firmware version, and steps to reproduce.

## Supported versions

Fixes land on the latest release. Please upgrade to the newest hub and firmware before reporting,
in case the issue is already resolved (see `CHANGELOG.md`).
