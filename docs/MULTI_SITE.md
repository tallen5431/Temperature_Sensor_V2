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
| `POST /api/ingest_csv` | the same endpoint, plus an optional `events` array |
| `X-Token` auth | the same auth |
| buffers to flash when the hub is down | backlog simply stays unsent |
| `UNIQUE(probe_id, epoch, site)` + `INSERT OR IGNORE` | the same index makes re-sends idempotent |

That last row carries the design. Because the receiver de-duplicates, a batch
re-sent after a dropped response **cannot** create duplicates. So the forwarder
never has to solve exactly-once delivery — it only has to guarantee it never
*skips*, and at-least-once comes free.

`site` is in that key, and it has to be. Probe ids are operator-visible strings:
two managers both naming their cooler `walkin` is the ordinary case, and without
site in the key head office silently discarded the second store's readings.

### Two records, not one

A store forwards **readings** and **alert events**, in the same request:

* **Readings** are what the sensor measured.
* **Events** are what that store's own alert engine *decided* — against that
  store's own thresholds. Head office re-evaluating the same readings against
  its own limits produces a different answer, and it is the store's answer an
  auditor asks for. So the store's event log travels with its readings, and the
  Recent-events feed filtered to a store shows what that store actually alerted
  on.

Events carry their own cursor, so neither stream can block the other, and they
share the request so one round trip advances both — either the batch lands or
neither cursor moves.

Event epochs are whole seconds, unlike readings' milliseconds, so their
uniqueness constraint is **partial**: it covers forwarded rows only
(`WHERE site != ''`). Constraining local events too would treat two genuinely
distinct same-second events as a replay and drop one, and a replay can only
happen on a forwarded batch anyway.

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

## Setting it up

**Settings → Multi-site**, on each hub. No file editing, no restart.

At **head office**, open that card and click *"Head office: show what my sites
need"*. It prints this hub's address and device token — the two values each site
has to be given. (It is behind a click because it reveals a secret, and because
it is irrelevant to the person configuring a store.)

At **each site**, turn on *"Send a copy of my readings to head office"* and fill
in the three fields: head office's address, this site's name, head office's
token. Save.

Saving does not just write a file — it **forwards immediately and tells you what
happened**:

> Saved — sent 1,284 readings to head office as "atlanta". Everything is up to date.

or, honestly:

> Saved, but nothing has reached head office yet. Head office rejected the token
> — check it matches head office's device token.

A saved setting that cannot reach head office must never look like a working one;
that is the whole reason the status line reports the live result rather than
"Saved". The card refuses outright to store a half-configuration — no address, no
site name, no token — because those are the states the forwarder silently does
nothing in.

Two things the form does quietly so nobody has to know the protocol: a site name
is **slugged**, not rejected (`Atlanta Store #2` → `atlanta-store-2`, echoed back
into the field so it matches what the dashboard shows), and a blank token keeps
the saved one, so re-saving other fields never wipes the credential. The token is
never sent back to the browser.

### The same settings in `config.json`

The UI writes this block; you can also write it directly (useful for imaging a
fleet of store hubs from one template):

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
| `batch` | Rows per request, capped at the protocol's 1000. Not on the form. |

`upstream.token` is redacted from `GET /api/config` like every other secret.

**Use HTTPS for `url` in production**, or a VPN. Readings are not secret but the
token is, and it rides in a header. Terminate TLS at HQ with a reverse proxy or a
tunnel — and see the warning in *Remote administration* below before exposing any
hub to the internet.

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
| probe claiming | `auto_provision` in its config, default **true** | turn it **off on the head-office hub** — see the warning below |

### 1. Start all three, one terminal each

```bash
mkdir -p /tmp/setpoint/{hq,store-atl,store-mar}

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

> ### ⚠ Two hubs on one LAN will fight over your probes
>
> This bites when the head-office hub and a store hub are on the **same
> network** — which is exactly what happens when you test across two machines at
> home, and never happens in a real deployment where stores sit on their own
> networks.
>
> Every hub runs an auto-provisioner (`auto_provision`, **on by default**) that
> discovers probes over mDNS every 10 s and, seeing a probe pointed at a
> *different* `server_url`, re-points it at itself. Two hubs on one LAN therefore
> take turns stealing the same probes, and readings land in whichever hub
> provisioned them most recently. It looks like forwarding is broken; it isn't.
>
> **On the head-office hub, set `auto_provision: false`.** An aggregating hub
> should never claim probes — it receives forwarded copies, not direct posts.
> That also makes the test faithful: every reading HQ holds then arrived by
> forwarding, which is what you are trying to verify.
>
> The tell: forwarded rows carry a site label, directly-posted ones do not.
> `scripts/site_report.py` shows both and names the problem outright.

### 2. Give the stores some readings

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

### 3. Turn on forwarding, from the UI

On **<http://127.0.0.1:8099/settings>** → Multi-site, flip *"Send a copy of my
readings to head office"* and enter:

| field | value |
|---|---|
| Head office hub address | `http://127.0.0.1:8098` |
| This site's name | `atlanta` |
| Head office token | `hq-token-abc123` |
| Send every | `5` (just to make the test feel live; 30 is the default) |

Save. The status line reports what actually happened, and the readings from step
2 go immediately — no restart:

> Saved — sent 9 readings to head office as "atlanta". Everything is up to date.

Repeat on **<http://127.0.0.1:8100/settings>** with the site name `marietta`.

Worth trying deliberately: save with the wrong token first. It stores the
settings but tells you the truth — *"Head office rejected the token"* — rather
than reporting success and leaving you to discover the gap later.

### 4. Watch it arrive

Each store's log shows the push:

```
INFO hub.forwarder: forwarded 2 readings to http://127.0.0.1:8098/api/ingest_csv as site=atlanta
```

and HQ's database has them labelled. `scripts/site_report.py` is the check you
will run most — it opens the store **read-only**, so it can never create or
change anything:

```bash
DATA_DIR=/tmp/setpoint/hq python scripts/site_report.py
```
```
readings : 27

  site                 probe                          rows   newest
  -------------------- ------------------------ ----------   -------------------
  atlanta              ATL-Freezer                       9   2026-08-04T08:45:48
  atlanta              ATL-Walkin                        9   2026-08-04T08:45:48
  marietta             MAR-Walkin                        9   2026-08-04T08:45:48

forwarded from : atlanta, marietta
local readings : 0
```

Run it on a **store** hub instead and it reports the other side — the backlog
still waiting to go:

```
forwarding     : ON -> http://127.0.0.1:8098 as "atlanta"
  sent so far  : up to row 300
  still to send: 200
```

Any row listed under site `(local)` **on the HQ hub** is a probe posting to head
office directly — see the auto-provision warning above.

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

- **No per-site alerting rules.** Alerts evaluate per probe as they always have,
  and each hub's thresholds are its own. Both hubs also alert independently: the
  store's monitor fires, and HQ's monitor separately evaluates the forwarded
  reading against HQ's thresholds. Usually what you want — store staff get
  theirs, the owner gets theirs — but put **different recipients** on each hub or
  one breach sends the same person two emails.
- **Renaming a site starts a new one.** Change `upstream.site` and HQ shows the
  new label alongside the old until the old rows age out; history is not
  relabelled.
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
