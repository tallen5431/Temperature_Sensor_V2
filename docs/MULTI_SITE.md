# Multi-site — how head office sees six stores

> **Status: implemented and testable end to end** — stores forward, and HQ's
> dashboard has a store picker that scopes the whole page.
> Code: [`core/forwarder.py`](../core/forwarder.py),
> [`components/dashboard_view.py`](../components/dashboard_view.py).
> Tests: `tests/test_forwarder.py`, `tests/test_multi_site_dashboard.py`.

## The question, and the trap

A chain with six stores asks: *"how does head office see all of them?"*

The obvious answer is to build a cloud, and it is the wrong one. "It can't be
shut down" and "your data stays on-prem" are why a buyer picks Setpoint over
SensorPush or Temp Stick. A hosted backend would invert the pitch, add permanent
uptime liability and cost to a one-person company, put you in the business of
holding other people's food-safety data, and pick a fight on the incumbents'
turf. There is a better answer that the architecture already almost had.

**Each store keeps its own hub and its own database. A store may additionally
*push a copy* of its readings to an aggregating hub head office runs.** Nothing
is taken away; something is added. The promise becomes "no *mandatory* cloud",
which is honest, and no store ever depends on head office being up.

---

## What to say on a sales call

> Each of your stores runs its own hub, so monitoring and alerts keep working in
> that store even if the internet drops — that is the point of the product. Each
> store also forwards a copy of its readings to a hub you run at head office, so
> you get one dashboard across all six, with history and alerts. The stores never
> accept an inbound connection, so there is nothing to open on their networks,
> and none of it goes through us. If you ever stopped paying us tomorrow, all of
> it keeps running.

That last sentence is the differentiator. Neither a purely local competitor nor a
cloud one can say it.

---

## How it works

A store hub forwarding to an HQ hub is the *same relationship* a probe already
has with a hub, which is why this is small:

| probe → hub | store hub → HQ hub |
|---|---|
| `POST /api/ingest_csv` | the same endpoint, unchanged |
| `X-Token` auth | the same auth |
| buffers to flash when the hub is down | backlog simply stays unsent |
| `UNIQUE(probe_id, epoch)` + `INSERT OR IGNORE` | the same index makes re-sends idempotent |

That last row carries the design. Because the receiver de-duplicates on
`(probe_id, epoch)`, a batch re-sent after a dropped response **cannot** create
duplicates. So the forwarder never has to solve exactly-once delivery — it only
has to guarantee it never *skips*, and at-least-once comes free.

**Push, never pull.** Stores need no inbound reachability: no tunnel, no port
forward, no VPN, nothing to secure per site. It also survives a store outage —
the cursor stops advancing and catches up later.

### Design decisions worth knowing

- **The cursor is `readings.id`, not a timestamp.** A probe draining a backlog
  writes *old* readings *now*; a timestamp cursor would skip them for being older
  than the mark. Insertion order is the only order that cannot lose a row.
- **Only local rows forward.** Rows that arrived here *from* another hub carry a
  `site` and are excluded, so two hubs pointed at each other cannot ping-pong the
  same readings forever.
- **The high-water mark is durable** (`meta` table), so a restart neither
  re-sends the whole history nor skips what was written while it was down.
- **A batch is labelled once** via the `X-Site` header, not per row. A forwarding
  hub sends only its own readings, so one label per batch cannot disagree with
  itself — and it works for the CSV body format too.
- **Refuses to run half-configured.** `upstream.enabled` without `upstream.site`
  logs and does nothing, rather than pooling six stores into one anonymous heap
  that no later migration could separate.

---

## Configuring a store hub

In that store's `config.json`:

```json
{
  "upstream": {
    "enabled": true,
    "url": "https://hq.example.com",
    "token": "<the HQ hub's device token>",
    "site": "atlanta",
    "interval_sec": 30,
    "batch": 500
  }
}
```

| Key | Meaning |
|---|---|
| `url` | HQ hub base URL. `/api/ingest_csv` is appended if absent. |
| `token` | HQ's device token — the same one HQ's own probes use. |
| `site` | Label for this store. `[A-Za-z0-9_-]`, 32 chars. **Required.** |
| `interval_sec` | Idle poll gap. A full batch drains immediately instead of waiting. |
| `batch` | Rows per request, capped at the protocol's 1000. |

`upstream.token` is redacted from `GET /api/config` like every other secret.

**Use HTTPS for `url` in production.** Readings are not secret, but the token is,
and it rides in a header. Terminate TLS at HQ with a reverse proxy or a tunnel.

---

## Test it locally with two hubs

This runs both roles on one machine, no network required. Verified end-to-end.

**1. Start an "HQ" hub** on port 8098 with a known token:

```bash
SETPOINT_DATA_DIR=/tmp/hq PORT=8098 SERVER_TOKEN=hq-token-abc123 python3 app.py
```

**2. Point a "store" hub at it and forward:**

```python
from core.db import Database
from core.config import Config
from core.forwarder import UpstreamForwarder
import datetime, pathlib

db  = Database(pathlib.Path("/tmp/store/temps.db"))
cfg = Config(pathlib.Path("/tmp/store/config.json"))
cfg.set("upstream", {"enabled": True, "url": "http://127.0.0.1:8098",
                     "token": "hq-token-abc123", "site": "atlanta"})

now = datetime.datetime.now()
for i in range(7):                                   # fake a freezer probe
    db.append((now + datetime.timedelta(seconds=i)).isoformat(timespec="milliseconds"),
              -18.4 + i * 0.05, 0.0, "Setpoint-9A3F2C")

f = UpstreamForwarder(db, cfg)
print(f.run_once())   # 7  — forwarded
print(f.run_once())   # 0  — cursor advanced, nothing to resend
```

**3. Confirm HQ received them, labelled:**

```bash
sqlite3 /tmp/hq/temperature_log.db \
  "SELECT site, COUNT(*) FROM readings GROUP BY site;"
# ''         <- HQ's own probes
# atlanta    <- forwarded from the store
```

Write more readings on the store side and call `run_once()` again — only the new
ones go. Stop the HQ hub mid-test and watch the cursor hold: nothing is lost, and
it catches up when HQ returns.

**4. Open HQ's dashboard** at <http://127.0.0.1:8098/>. A **Site** control now
sits beside "Viewing" (it was hidden before the first forward arrived). Repeat
step 2 with `"site": "marietta"` and different temperatures to get a second
store, then switch between them: every number, card and series on the page should
move together. If any one of them disagrees with the picker, that is a bug —
`tests/test_multi_site_dashboard.py` pins each surface.

---

## The HQ dashboard

A **Site** picker appears next to "Viewing" in the focus bar. It is populated
from `Database.sites()`, so it stays **invisible on a hub no one forwards to** —
which is every hub until a chain runs one. Single-site users never learn the
control exists.

Selecting a store scopes the entire page, not part of it:

| | scoped to the selected store |
|---|---|
| Temperature chart | ✅ |
| Min / Max / Average | ✅ |
| "Showing X of Y data points" (both numbers) | ✅ |
| Probe status cards | ✅ |
| Per-probe statistics | ✅ |
| Humidity / VPD cards | ✅ |
| Current-temperature gauge | ✅ |
| "Connected Probes" KPI | ✅ |
| "Last Update" KPI | ✅ |
| Recent events feed | ✅ |
| "Viewing" probe dropdown | ✅ (and a focus the store no longer contains resets to *All probes*) |

**Three things deliberately do not filter**, and each would be a bug if it did:

- **Alerts.** A breach in Savannah is still a breach while head office is looking
  at Atlanta. The alert scan and the banner stay hub-wide.
- **`/metrics`, `/api/probes`, `/api/health`.** A Prometheus scrape wants the
  hub, not whatever a browser tab happens to be showing. `reporting_probe_ids()`
  takes an optional `site` only for the KPI; every machine-facing caller leaves it
  unset.
- **The footer's "N probes online".** It is a hub health indicator shared with
  Devices, Settings and Diagnostics, none of which have a site context.

Cards belonging to a forwarding store carry a `⌂ store` line. HQ's own probes get
no badge, so a single-site hub's cards are byte-for-byte what they were.

**Probe names are per hub.** `probe_names` lives in HQ's own `config.json`, so a
forwarded probe shows its raw id (`Setpoint-9A3F2C`) until someone names it at
HQ. Naming it in the store's hub does not carry across — only readings forward.

---

## What is not built yet

Honest list, so nobody sells past it:

- **No per-site alerting rules.** Alerts evaluate per probe as they always have.
- **Sites are not renameable from the UI.** The label is whatever the store hub's
  `upstream.site` says; changing it there makes HQ show a new store alongside the
  old one until the old rows age out.
- **No remote administration.** Changing a store's thresholds still means reaching
  that store's hub. See below.
- **Site is sender-declared.** The token authenticates the store; the label is
  self-reported. Fine inside one company. If that ever matters, give each store
  its own token and have HQ map token → site.

## Remote administration, when you need it

Forwarding solves *aggregation*. It does not let someone at HQ open store 3's
live dashboard or change its thresholds. When that comes up, expose that store's
hub through a tunnel — **on the customer's own Cloudflare account and domain,
never yours.** If stores tunnel through `datumlaboratories.com`, their monitoring
depends on your domain and your account, and you become exactly the vendor who
can brick them. Set it up as part of a paid install; they own the result.

**Whatever you use, put an authenticating proxy in front.** `ui_auth` does not
cover everything: `SECURITY.md` documents that `/metrics`, `/api/probes`,
`/api/health` and `/api/diagnostics` stay open by design so Prometheus can
scrape. A bare tunnel publishes probe IDs, live temperatures and hub diagnostics
to anyone who learns the URL. Use Cloudflare Access in front, or Tailscale so
nothing is public at all.

## The third option, free

A customer with an ops team can point their own Prometheus at each store and get
Grafana dashboards and cross-site alerting with no work from you — `/metrics`
already exists on every hub. Worth a line in the sales conversation; it costs a
README section and answers the most technical buyer in the room.
