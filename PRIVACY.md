# Privacy

_Last updated: 2026_

> **Note for the maker/reseller:** ThermaHub is a white-label product. Before you
> ship, replace **ThermaHub** with your product name and swap the support link
> (`https://example.com/support`) for your own — it must match the `support_url`
> in your `branding` config.

**Short version: ThermaHub does not collect your data. There is no cloud, no
account, and no telemetry. Your temperature readings stay on your own PC.**

## What ThermaHub is

ThermaHub is a local-first temperature-monitoring appliance. It runs as a small
app on your own Windows or Linux computer. Wireless ThermaProbe sensors on your
own network send their readings to it, and you view everything in your web
browser at `http://localhost:8080`. Nothing is hosted by us, and there is
nothing to sign up for.

## What we collect: nothing

- **No account.** You never create a login, and you never give us your name,
  email, or payment details to run the software.
- **No cloud.** ThermaHub does not upload your readings anywhere. There is no
  ThermaHub server to receive them.
- **No telemetry.** The software does not phone home. It does not send usage
  statistics, crash reports, analytics, device fingerprints, or "check for
  updates" pings to us or to anyone else.

## Where your data lives

Everything ThermaHub stores stays on the computer you run it on:

- **`temperature_log.csv`** — your temperature history. Columns are
  `timestamp,temperature_c,temperature_f,probe_id`. This is a plain text file
  you can open in Excel, Google Sheets, or any editor. You can back it up,
  move it, or delete it at any time. It is the only file offered for download
  from the dashboard (`/download/temperature_log.csv`).
- **`config.json` / `config.local.json`** — your settings: probe names,
  calibration, alert thresholds, notification settings, and your private device
  token. `config.local.json` holds the token and any secrets (such as an SMTP
  password) and should not be shared.

To erase your data, stop the hub and delete these files. There is no server-side
copy anywhere.

## What talks to what on your network

- **Hub <-> probes only.** The hub discovers ThermaProbe sensors on your local
  network (mDNS/zeroconf) and receives their readings over plain HTTP on your
  LAN. The hub and probes only ever talk to each other on your own network.
- **A private device token** is generated on first run and shared only with your
  own probes so that no other device can push fake readings to your hub.
- **The dashboard** is served locally at `http://localhost:8080`. If you allow
  it through your firewall on a Private network, other PCs on your own network
  can view it — that is your choice, not a default upload to the internet.

ThermaHub does not need internet access to do its job. It works fully offline.

## The optional email / webhook alerts

Alerts are **off by default**. If you turn them on (in the notifications
settings), and only then, ThermaHub will contact the destination **you**
configure — nobody else:

- **Email alerts** are sent through **your own SMTP server** (the `smtp_host`,
  `smtp_user`, etc. that you enter) to the `recipients` you list. The message
  contains only what is needed for the alert: the product/brand name, the probe
  name or ID, the reading that crossed your threshold, the threshold, and a
  timestamp. Your SMTP credentials are used only to send that mail and are
  stored locally in your config.
- **Webhook alerts** send a small JSON payload to the `webhook_url` **you**
  enter (for example your own Slack, Discord, or home-automation endpoint). The
  payload describes the same alert event (probe, reading, threshold, time).

We do not see, proxy, or receive any of this. It goes directly from your PC to
the mail server or URL you chose. If you never enter a recipient or webhook, no
alert traffic ever leaves your machine.

## Children

ThermaHub is a monitoring appliance, not directed at children, and it collects
no personal information from anyone.

## Changes

If this policy changes, the updated version ships with the product. Because
there is no account and no cloud, there is no data for us to retroactively
collect regardless of any change.

## Contact

Questions about privacy? Reach us at **https://example.com/support**.
