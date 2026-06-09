# Security Policy

## Reporting a vulnerability

Please report security issues privately rather than opening a public issue.
Use GitHub's **Report a vulnerability** (Security → Advisories) on this
repository, or contact the maintainer directly. We aim to acknowledge reports
within a few business days and will keep you updated on a fix.

When reporting, include the hub version (see the **Diagnostics** page or
`/api/diagnostics`), firmware version, and steps to reproduce.

## Deploying safely

The hub serves a dashboard and write API on your LAN. For anything beyond a
trusted home network:

- **Set `SERVER_TOKEN`.** When set, every API write (`/api/ingest`,
  `/api/provision`, `POST /api/config`) requires the `X-Token` header; the
  auto-provisioner pushes the token to probes automatically.
- **Keep it on a trusted network.** There is no user login; treat dashboard
  access as equivalent to LAN access. Do not port-forward the hub to the public
  internet.
- **Secrets stay local.** Notification passwords/tokens live only in
  `config.json` next to the app. `GET /api/config` redacts them and
  `/api/diagnostics` reports channels as on/off only — neither exposes secret
  values.

## Supported versions

Fixes land on the latest release. Please upgrade to the newest hub and firmware
before reporting, in case the issue is already resolved (see `CHANGELOG.md`).
