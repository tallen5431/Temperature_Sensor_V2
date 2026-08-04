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

## Test it locally with three hubs

Head office plus two stores, all on one machine, no network and no hardware
required. Verified end to end — the transcript below is a real run.

Three things a hub keeps apart, which is what makes this work:

| | set by | why it matters here |
|---|---|---|
| data directory | `DATA_DIR` env var | **not** `SETPOINT_DATA_DIR`. Omit it and all three hubs share one database and one config, and the test is meaningless. |
| port | `PORT` env var | default 8088 |
| device token | `SERVER_TOKEN` env var, else `provision_token` in its config | each hub has its own; the store's `upstream.token` must be **HQ's**, not its own |

### 1. Lay out three data directories

`upstream` is not on the Settings page yet, so a store's block is a hand-edit of
its `config.json`. Writing the file *before* first start also skips a restart —
the forwarder thread is only launched at boot if `upstream.enabled` is already
true.

```bash
mkdir -p /tmp/setpoint/{hq,store-atl,store-mar}

cat > /tmp/setpoint/store-atl/config.json <<'JSON'
{
  "provision_token": "atlanta-local-token",
  "upstream": {
    "enabled": true,
    "url": "http://127.0.0.1:8098",
    "token": "hq-token-abc123",
    "site": "atlanta",
    "interval_sec": 5
  }
}
JSON

sed 's/atlanta/marietta/g' /tmp/setpoint/store-atl/config.json \
  > /tmp/setpoint/store-mar/config.json
```

`interval_sec: 5` just makes the test feel live; 30 is the default and is right
in production.

### 2. Start all three, one terminal each

```bash
# head office
DATA_DIR=/tmp/setpoint/hq        PORT=8098 SERVER_TOKEN=hq-token-abc123      MDNS_ENABLE=0 python app.py
# store 1
DATA_DIR=/tmp/setpoint/store-atl PORT=8099 SERVER_TOKEN=atlanta-local-token  MDNS_ENABLE=0 python app.py
# store 2
DATA_DIR=/tmp/setpoint/store-mar PORT=8100 SERVER_TOKEN=marietta-local-token MDNS_ENABLE=0 python app.py
```

<details><summary>PowerShell (Windows)</summary>

```powershell
$env:DATA_DIR="$env:TEMP\setpoint\hq"; $env:PORT="8098"
$env:SERVER_TOKEN="hq-token-abc123";   $env:MDNS_ENABLE="0"; python app.py
```
Use a separate PowerShell window per hub — `$env:` persists for that window.
</details>

`MDNS_ENABLE=0` keeps three hubs on one machine from advertising the same
service and discovering each other. Leave it on in real deployments.

Each store logs the forwarder at startup — this line is the confirmation that
its config was read:

```
INFO hub.forwarder: upstream forwarder started
INFO hub.app: Upstream forwarder started (site=atlanta -> http://127.0.0.1:8098)
```

If it is missing, `upstream.enabled` is not `true` in that hub's config.json, or
you edited the wrong directory.

### 3. Give the stores some readings

No probes needed — `scripts/simulate_probe.py` posts as one. Note each store
takes its **own** token here:

```bash
python scripts/simulate_probe.py --url http://127.0.0.1:8099 \
  --token atlanta-local-token --probe ATL-Walkin  --temp 3.4
python scripts/simulate_probe.py --url http://127.0.0.1:8099 \
  --token atlanta-local-token --probe ATL-Freezer --temp -18.2
python scripts/simulate_probe.py --url http://127.0.0.1:8100 \
  --token marietta-local-token --probe MAR-Walkin --temp 4.1
```

Or run a ramp to watch a live series build and an alert fire:

```bash
python scripts/simulate_probe.py --url http://127.0.0.1:8099 \
  --token atlanta-local-token --probe ATL-Walkin --from 3 --to 12 --step 0.5 --interval 5
```

Real hardware works too: flash a probe pointing at `http://<this-pc>:8099`.

### 4. Watch it arrive

Within `interval_sec`, each store's log shows the push:

```
INFO hub.forwarder: forwarded 2 readings to http://127.0.0.1:8098/api/ingest_csv as site=atlanta
```

and HQ's database has them labelled:

```bash
python -c "import sqlite3;print(*sqlite3.connect('/tmp/setpoint/hq/temperature_log.db')
  .execute('SELECT site,probe_id,COUNT(*) FROM readings GROUP BY site,probe_id'),sep='\n')"
# ('atlanta',  'ATL-Freezer', 9)
# ('atlanta',  'ATL-Walkin',  9)
# ('marietta', 'MAR-Walkin',  9)
```

### 5. Open the dashboards

**HQ — <http://127.0.0.1:8098/>.** A **Site** control now sits beside "Viewing"
reading *All sites (2)*, and each card carries a `⌂ atlanta` / `⌂ marietta` line.
Pick a store: every number, card and series on the page should move together —
Connected Probes, Last Update, the gauge, Min/Max/Average, "Showing X of Y", the
probe cards, per-probe statistics and the events feed. If any one of them
disagrees with the picker, that is a bug; `tests/test_multi_site_dashboard.py`
pins each surface individually.

**A store — <http://127.0.0.1:8099/>.** No Site control at all (it never
received a forward, so it has no sites), and no `⌂` badges. This is the check
that matters most: a single-site customer's dashboard must be untouched.

### Worth trying while it's running

- **Kill HQ**, post more readings to a store, restart HQ. The store logs
  `no response; N readings held, retrying in 10s` and holds its cursor; when HQ
  returns everything lands. Verified: 12 readings written during an outage, 12
  arrived, 0 lost.
- **Force a full replay.** Rewind a store's high-water mark and watch HQ's row
  count *not* move — `UNIQUE(probe_id, epoch)` + `INSERT OR IGNORE` make
  re-sends idempotent, which is what lets the forwarder settle for
  at-least-once delivery instead of solving exactly-once:

  ```bash
  python -c "from core.db import Database; import pathlib
  Database(pathlib.Path('/tmp/setpoint/store-atl/temperature_log.db')) \
      .meta_set('forwarder.last_id','0')"
  ```
  Verified: 29 readings re-sent, 0 duplicates created.
- **Point the stores at each other** instead of HQ (`url` → each other's port).
  They do not ping-pong — rows that arrived *from* another hub carry a `site` and
  are excluded from forwarding.
- **Blank `"site"`** in a store's config and restart. It refuses to forward and
  logs why, rather than pooling stores into one anonymous heap that no later
  migration could separate.

### Tearing down

Stop the three processes and `rm -rf /tmp/setpoint`. Nothing was written outside
that directory — your real hub's data directory is untouched.

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
