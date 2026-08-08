# Changelog

All notable changes to Setpoint (the PC-side hub application) and its Setpoint
ESP32 firmware are documented in this file. (Earlier entries below predate the
rebrand and refer to the product by its former name, "TempSensor".)

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **Head office sent false alarms about healthy stores.** A multi-site hub holds
  every store's readings but none of their configuration — thresholds, reporting
  intervals and calibration are per hub and are not forwarded, and there is
  nowhere for them to go if they were. The hub re-derived alarms from forwarded
  readings anyway, applying its own settings to somebody else's probes:

  * an HQ that runs fridges (0–8 °C) mailed a **LOW** alarm for every healthy
    store freezer sitting at −19 °C, and rendered the same false verdict on its
    dashboard card;
  * a store probe on a 15-minute deep-sleep cadence was judged against HQ's own
    300 s freshness window and called **offline** while working perfectly (the
    store hub, which knows the cadence, correctly said nothing);
  * every genuine store breach landed in HQ's event log **twice** — once
    forwarded from the store, once re-derived here.

  On an alerting product this is the worst kind of wrong: a head office whose
  mail is mostly false is a head office that stops reading it. The store hub is
  the authority on its own probes — it holds the limits, the cooldown and the
  deadband, and forwards the resulting events. Head office aggregates and
  displays them. Forwarded readings stay fully visible on the dashboard, chart,
  exports and event log; they are simply not re-judged.
- **Head office now shows the verdict the store sent it.** Having stopped
  re-judging forwarded probes (above), head office had nothing to say about them
  — it drew a store freezer sitting in a live breach as "no alarm set" while the
  store's own screen showed "▲ HIGH". One probe, one moment, two hubs, two
  answers. The store forwards the verdict it reached and head office holds that
  event, so the card now uses it and names whose finding it is: **▲ HIGH ·
  store1**. A `recovery` clears it; a `missed` never sets it, because that
  records an excursion which has already ended and would otherwise leave a probe
  looking broken forever after one bad night.
- **The Dashboard and Devices pages disagreed about whether a probe was
  watched.** The alert engine resolves a probe's limits as "its own entry, else
  `default`". The Dashboard card did the same; the Devices card looked up the
  per-probe entry only — so on a hub configured with a `default`, one page showed
  "▼ LOW" and the other "Alarm range not set", for the same probe at the same
  moment. The Devices answer was the dangerous direction: it reads as "nothing is
  watching this probe" about one that will alarm. Both now go through
  `core.status.limits_for`, which is also where the forwarded-probe rule above
  lives, so the two questions have one answer each.

- **The browser tab showed Plotly's logo, not Setpoint's.** `assets/favicon.ico`
  never existed, so Dash's `{%favicon%}` template token fell back to the copy it
  ships with the library — a Plotly logo, on every page, in every bookmark, and
  on every "Add to Home Screen" icon. Built from `assets/logo.svg` (the same mark
  already used in the navbar) at the six sizes a browser actually asks for.
  `tests/test_favicon.py` pins that the file exists, is well-formed, carries a
  16×16 entry (the size a tab renders), and — the literal regression — is not
  byte-identical to Dash's bundled default.

## [2.7.2] - 2026-08-07

### Fixed

- **An excursion that started and ended between two alert cycles raised nothing
  at all.** The alert engine judges one reading per probe per cycle — the latest.
  A breach that began and cleared in between was written to the database, drawn
  on the chart, and never alerted, logged, or shown as an event. On a monitoring
  product that is the worst shape a bug can take: the evidence sits there and
  nobody was told.

  It is not a corner case, and the threshold watch made it the *normal* shape of
  a hub outage. A watching probe buffers every sample to flash while it cannot
  reach the hub, then flushes the lot on reconnect — so a freezer that failed and
  recovered while the PC was asleep, restarting, or off the network arrived
  entirely as history and passed straight through the alert engine. The watch
  exists so an excursion between *reports* is not missed; the hub end was giving
  that back.

  Each backfill is now scanned forward from the last reading already examined —
  by ARRIVAL (`readings.id`), not by timestamp. A backlog is old by timestamp and
  new by arrival, so a watermark on time cannot see one at all: "nothing newer
  than last time" is exactly what a flush looks like, and the hub restart that
  ends an outage is followed immediately by the flush that outage caused.
  A closed excursion becomes **one** event — 13 minutes at a 7 s cadence is 110
  readings and one problem — carrying the worst reading it reached, logged and
  dated at the time it *happened* rather than when it was discovered, and shown as
  **WAS OUT OF RANGE** so it cannot be mistaken for a live alarm. The message is
  past tense and explains that the readings arrived late. A run still open at the
  newest reading is deliberately left to the live evaluator, which owns the
  cooldown and deadband for it, so the two can never both report one incident.
  First sight of a probe seeds the watermark without scanning, so restarting the
  hub does not re-announce every excursion still in retention, and a long backfill
  is capped per sweep with a log line naming what was dropped.

  `POST /api/ingest_csv` no longer logs backfill breaches itself. It recorded the
  worst excursion **per batch**, and a probe drains a backlog in 100-row chunks —
  a twelve-hour outage at a 7 s cadence is 62 chunks, so one thawing freezer
  produced up to 62 event rows, each labelled "worst in this chunk". It also never
  notified, on the grounds that a backfilled breach is "old news"; a freezer that
  spent thirteen minutes above its limit last night is not old news. And it could
  not cover a probe reconnecting one reading at a time through `/api/ingest`. One
  owner now, on the monitor thread where the work belongs.

  This landed after `v2.7.1` was tagged, so that release does **not** contain it —
  it was written into the `[2.7.1]` section below while 2.7.1 was still
  unreleased, which is exactly the wrong place for it now. `v2.7.1` and this
  hub's running code briefly disagreed about what "2.7.1" contained; this bump
  is what closes that.

## [Firmware 2.9.3] - 2026-08-07

### Changed

- **The Wi-Fi setup portal says "Reporting interval (ms)", not "Read interval".**
  It sets `cfg_interval`, which is how often the probe *transmits*; with the
  threshold watch armed the probe reads far more often than that. This is the one
  screen every customer passes through, and it disagreed with the dashboard field
  it mirrors.

  No behaviour changed — this is one string. The version moved because
  `.github/workflows/deploy-flasher.yml` rebuilds the merged binary **in CI** from
  this `.ino` on every push touching `esp32_temp_probe/**` or `flash/**`, and
  copies `flash/manifest.json` through verbatim. The push carrying the string
  change therefore republished the flasher with a new image still advertised as
  2.9.2, so that number briefly named two binaries — exactly the drift
  `tests/test_version_sync.py` exists to prevent. Bumping all four declarations
  (RELEASE.md step 1) is what closes it; probes already in the field will see an
  update available.

  Still true of 2.9.2 and 2.9.3 alike: **neither has been validated on real
  ESP32-C3 hardware.** `deploy-flasher.yml`'s own note says to treat an
  un-validated deploy as staging — run `docs/QC_CHECKLIST.md` on a unit before
  pointing buyers at it.

## [2.7.1] - 2026-08-07

### Added

- **The between-report check has a control.** A probe has two cadences: how often
  it transmits, and — for probes with a limit set — how often it reads the sensor
  in between with its radio off, sending immediately if a reading crosses that
  limit. The second one (`probe_sample_sec`) had no UI at all and could only be
  changed by editing `config.json`, so the threshold watch could not be turned on
  from the app. It is now **Settings → Probes → Check the sensor every**, with a
  live line naming the probes it currently reaches — because the setting is inert
  unless a probe reports *less* often than it, and the shipped defaults (60 s
  check, 5 s reporting interval) are exactly that case, so "Saved" on its own says
  nothing about whether anything happens. The section badge reports the cadence
  only when it reaches at least one probe.
- **Each probe can check at its own cadence.** One number for the fleet forces the
  slowest acceptable cadence onto everything: a walk-in cooler on mains can afford
  to look every 10 s, a battery probe in a remote freezer on a 15-minute report
  cannot, and every extra wake is run time it does not get back. **Devices → Edit →
  Check between reports every** stores a per-probe override in `probe_samples`,
  in the same shape as `probe_intervals` and `probe_resolutions`; blank inherits
  the hub default, and is stored by removing the entry so an inheriting probe keeps
  following later fleet-wide changes. The Settings line counts only the probes the
  default actually reaches and names the ones on their own cadence separately, so a
  fleet number cannot look wrong when it is not. No firmware change: the probe was
  already told its own `sample_ms`, and persists it in NVS.
- **The Devices card says whether a probe checks between reports.** "Reports every
  15 minutes" while checking every 10 s and "reports every 15 minutes" flat are
  very different promises about a freezer, and the card rendered them identically.
  Shown only while the watch is armed, and now that the cadence is per probe it
  cannot be inferred from one hub-wide setting either.
- **The Save button pushes the watch, not just the interval.** The immediate
  best-effort re-provision sent the reporting interval and sensor resolution but
  not the limits or check cadence, so a check-cadence change was the one edit it
  could not deliver — it waited for the probe's next check-in. It now sends the
  same `desired_probe_config` the `/api/ingest` reply answers with, so a probe
  reached by the push and one that pulls cannot end up configured differently.
- **The friendly probe name is in the plain CSV export.** The spreadsheet export
  has always carried a `probe` column; the **Download CSV** button's file
  identified a fridge only as `Setpoint-000092`, and `app.py` was already reading
  the names for the other export. Conditional on a name actually being set, like
  the `site` and humidity columns, so a hub that has named nothing writes the file
  it always wrote.

### Changed

- **"Read Interval" on Devices → Edit is now "Reporting Interval".** It sets how
  often the probe *transmits*; with the watch armed the probe reads far more often
  than that, which is the entire point of having two numbers. A field named for
  one and setting the other left no way to tell them apart — or to ask which a
  probe was on. The dialog now also states, live as you type, whether this probe
  checks between reports and at what cadence, or what is missing if it does not.

### Fixed

- **PROTOCOL.md described a wire that stopped existing two releases ago.** It said
  the `/api/ingest` config reply was "deliberately limited to `interval_ms` and
  `resolution_bits`"; the hub has sent `alert_min_c`, `alert_max_c` and `sample_ms`
  in it since 2.6.2, and those three ARE the threshold watch. `GET /status`'s watch
  fields — which the auto-provisioner reads to decide whether a probe needs
  re-provisioning — were undocumented entirely, and the `/provision` push body was
  three fields short. Anyone writing a second firmware against that text would have
  produced a probe that looked correct and watched nothing. The watch now has its
  own section (§5.3), and `tests/test_protocol_doc.py` checks the documented field
  lists against `desired_probe_config` rather than asking anyone to proofread —
  this was the fourth doc/code pair in this repo to drift while a comment asked a
  human to keep them in step.
- **One name for one thing.** The dashboard field was renamed to "Reporting
  Interval", but the probe's own Wi-Fi setup portal and four docs still called it
  the "read interval" — so a customer reading "read interval ≥ 10 s" in VERSIONS.md
  would find no such field anywhere in the app. Renamed throughout, with a test
  that fails on the next one. (The portal string is a firmware change; see
  Unreleased above.)
- **The dashboard no longer goes blank after visiting Devices.** Opening Devices
  and then returning to the dashboard — by browser Back, or by any route that
  unmounted the Devices page — left the whole page empty: no gauge, no chart, no
  KPIs, no probe cards. Only a manual reload brought it back. `DevicesLayout`
  carried its own `dcc.Store(id='temp-unit-store')`, left over from when that
  store lived on the dashboard and only one page mounted it at a time. The store
  later moved to the app shell, which mounts it on *every* page, so the copy on
  Devices became a second live component sharing one id. Dash keys components by
  id: opening Devices pointed that id at the copy inside `page-content`, and
  navigating away tore the subtree down and deleted the entry with it, leaving
  the shell's still-mounted store unreachable. `update_dashboard` reads
  `temp-unit-store` as an Input, so it stopped firing entirely. The page's copy
  is gone; every page now reads the shell's store, which was the point of moving
  it up. `tests/test_callback_graph.py` now fails if any route re-declares an id
  the shell already mounts — a check Dash itself cannot do, because it validates
  `app.layout` at startup while `page-content` is still empty.
- **°C / °F / K and 24h / 12h are kept.** Choosing °F held until the next page
  load, then silently reverted. Every load fired the two toggle callbacks as
  though their buttons had been pressed — `prevent_initial_call=True` does not
  cover a button that a callback inserts into the layout, and Dash fires a
  newly-inserted subtree's callbacks with `n_clicks` still unset — so they wrote
  "celsius" and "24h" over whatever had been chosen. They now ignore a trigger
  carrying no click count. This also brings back the locale defaults, which had
  never once run: they only write while the preference is still unset, and the
  toggles were filling it in first, so a US customer got °C on a 24-hour clock
  no matter what their browser said.
- **The unit and clock buttons show the setting that is actually in effect.**
  After a reload the °C and 24h buttons stayed lit while the gauge, chart, probe
  cards and statistics all correctly used the saved preference — a page reading
  °F everywhere with °C highlighted, which is indistinguishable from the setting
  not being kept. Their only Input was the preference store in the app shell, and
  dash-renderer queues a mounting page's callbacks by Input, so neither ever ran
  on a page load; the buttons kept the layout's hard-coded default. Both now take
  the dashboard's own refresh tick as well, so they mount with the page, and both
  moved clientside so that costs no server round-trips.

## [2.7.0] - 2026-08-06

### Changed

- **Settings is a collapsed index instead of six stacked forms.** Every area —
  Alerts & notifications, Probes, Set up a new probe, Data & storage,
  Integrations, Multi-site — is now a card that opens on click, with a one-line
  description and a live badge saying what it is set to right now ("Off",
  "Email + Webhook", "Keep 90 days", "Sending as *atlanta*"). The page opens as
  six readable lines, so the answer to "what is this hub actually doing?" no
  longer requires scrolling past every setting the hub has. Badges deliberately
  reflect **saved** config, and read "On · no channel" / "Email not finished"
  rather than green, so a half-configured section can never look finished. All
  section bodies stay mounted, so nothing about how settings save changed.
- **Alerts asks for three things instead of eighteen.** Visible: enable, where
  to send (email/webhook), and whether to alert when a probe stops reporting.
  Re-alert interval, deadband, offline window, back-online confirmation, rate
  alert and recovery notices all already had sensible defaults and now live
  behind **Advanced settings** in the same card.
- **The Devices edit modal leads with what edits are for.** Friendly name and
  the two alert limits are visible; sensor resolution and calibration offset —
  and their several paragraphs of explanation — moved behind **Advanced**.
- **Dashboard reading order is now urgency order.** Alerts → hub KPIs → per-probe
  cards → gauge and chart → statistics. The gauge and chart previously sat below
  five stacked sections, making the most-looked-at element on the page also the
  furthest down it. Secondary reads (per-probe breakdown, humidity/VPD, Recent
  events) fold behind one **More detail** toggle whose state persists per
  browser — and their callbacks are gated on it, so a closed section no longer
  runs a per-probe `GROUP BY` over the selected range every 5 seconds.
- **The °C/°F/K picker left the KPI row.** It was a control dressed as a metric,
  sitting among the readouts; it now sits with the other view controls in the
  toolbar next to the clock format.

### Added

- **Demo data now demonstrates the product, not a thermometer.** The two demo
  probes arrive with the alarm range their role implies (Demo Fridge 1–5 °C,
  Demo Room 18–25 °C), so the cards show a range, a green OK earned against it,
  and the alerting the hub exists for. Their sine wave was also wider than the
  band it is now held to, which drew a line poking over its own limit with no
  event recorded against it — the monitor only evaluates the newest reading — so
  the demo's most visible moment read as alerting that missed an excursion.
  Clearing the demo removes the thresholds along with everything else `DEMO-`.
- **SMTP settings are inferred from the email address.** Typing
  `you@gmail.com` fills in `smtp.gmail.com:587` with STARTTLS; ~30 provider
  domains are covered (Gmail, Outlook, Yahoo, iCloud, Fastmail, Zoho, Proton
  Bridge, the major US ISPs, …) and anything else falls back to
  `smtp.<domain>:587`, clearly labelled as a guess rather than stated as fact.
  Providers that reject account passwords say so on the spot — "Gmail needs an
  App Password" is the single most common reason a correct-looking email setup
  never delivers. The host/port/encryption stay editable under **Server
  settings** and a hand-entered host is never overwritten.
- **Blank From/To addresses fall back to the account address.** A blank `to` was
  not a neutral default: `send_email` refuses to send without a recipient, so it
  produced an email channel that looked configured and silently never delivered.
- **The webhook URL is recognised** — Slack, Discord, Teams, Google Chat,
  Zapier, IFTTT, PagerDuty, Pushover, ntfy — and named back to the operator, so
  a typo'd URL is visible before the test send rather than after it.
- **Unit and clock format default to the browser's locale.** A US customer's
  first view is already °F on a 12-hour clock; everyone else keeps °C / 24 h.
  Detected clientside, only while the browser has never chosen, and an explicit
  choice is never second-guessed.
- **A new site's name defaults to this machine's hostname** (slugged, with a
  trailing `-hub`/`-pi`/`-server` trimmed), instead of asking for a label the
  hub already knows.
- **A regression guard for dangling callback ids.** `suppress_callback_exceptions`
  is required here (pages are served per route), and its cost is that renaming a
  component id breaks the callback reading it with no error anywhere — the
  control simply stops working. A new test walks every route's real component
  tree and fails on the first callback pointing at an id no page renders.

### Fixed

- **If the alert monitor thread died, nothing noticed.** This is the worst
  failure the product has and it was the one with no detector. Every other signal
  keeps looking correct while it is happening: readings are written on the
  *request* thread, so `rows_written` climbs and `last_write_age_sec` stays
  small; the dashboard draws live cards and a moving chart; `/api/health`
  reported `healthy: true`; `setpoint_healthy` stayed at 1, so a Grafana alert
  wired to it stayed quiet; and the Diagnostics page said "Healthy". Meanwhile no
  alarm can ever be raised again. The existing `HealthState` counters could not
  help — they only record failures something *live* observed, and the thing that
  would have observed this one is the thing that stopped. The hub now registers
  its background threads and reports them: `/api/health` gains `workers` and
  `workers_down`, `/metrics` gains `setpoint_worker_up{worker="…"}`, and a dead
  **required** worker (the alert monitor, and only it) forces `healthy: false`.
  The Diagnostics page says what it means in words — "Alerting has stopped… no
  alarm will be raised… restart the hub" — because "1 of 3 running" is a fact
  nobody can act on. The auto-provisioner and the upstream forwarder are
  reported but do not condemn the hub: stopped, those are degraded, not blind.
- **Firmware v2.9.2 — the deep-sleep clock ran slow by the shutdown tail on
  every wake.** `enterDeepSleep()` checkpointed the pre-sleep instant at the top
  of the function, then flushed Serial, tore down HTTP and mDNS, called
  `WiFi.disconnect()` and waited 20 ms — all of it after the recorded instant and
  before the wake timer started. The wake-side reconstruction
  (`rtc_epochMsAtSleep + rtc_sleepMs + millis()`) never added that back, so the
  clock lost it on every single wake, in one direction, accumulating rather than
  averaging out. The checkpoint is now taken last, immediately before the timer
  is armed. An NTP resync bounds the error while the probe is **online**, but a
  resync needs a connected wake — so through a router or hub outage, which is
  exactly when readings are being buffered and their timestamps are the only
  record of when they were taken, it free-ran.

  A second uncounted interval remains and is **not** fixed: the ROM and
  second-stage bootloader run before `millis()` starts counting, so each wake
  also loses ~100–300 ms. On the numbers that is the larger of the two.
  Measuring it needs the continuously-running RTC tick counter instead of
  `millis()`, which is worth doing on a bench where the result can be checked
  against a reference clock rather than changed blind. Documented at the restore
  site so it is recorded rather than folklore.
- **Replaying a drained buffer chunk is only free for rows that carry a
  timestamp.** Three places — `bufferFlush()`'s comment, the firmware's v2.8.1
  header note, and PROTOCOL.md §7 — stated that a re-sent chunk after a dropped
  ACK is always deduped by `UNIQUE(probe_id, epoch, site)`. That holds for
  stamped rows (measured: five sent three times store five). It does **not** hold
  for rows the hub receipt-stamps on arrival, which since firmware 2.8.2 means
  any reading buffered by a probe whose clock never synced — the local-first,
  no-internet deployment this product is sold for. A replay gets new stamps, new
  epochs, and lands as duplicates (measured: five sent three times stored
  **eight**, partly deduped only where receipt stamps collided by chance, so the
  surplus is not even predictable). `bufferAppend` was changed in 2.8.2 to accept
  an empty stamp *deliberately* — the alternative was dropping the reading
  outright, which was worse — but the comment claiming it "refuses an empty one"
  was never updated. All three now describe what actually happens, both halves
  are pinned by tests, and PROTOCOL.md records that closing it needs a stable
  per-row ordinal in the buffer format (a wire change), while noting that hashing
  the chunk body is not a fix: a freezer holding steady produces byte-identical
  consecutive chunks legitimately.
- **The first "requests are queuing" notice was swallowed on a freshly-booted
  machine.** The throttle added above seeded its last-emitted time to `0.0` and
  compared it against `time.monotonic()`, which counts from **system boot** — so
  for the first five minutes of uptime the notice was suppressed rather than
  shown. That is exactly a hub configured to start on boot or login, at the one
  moment it is most likely to be saturated: every probe rejoining at once. Caught
  by the test container happening to be 294 s old.
- **Firmware v2.9.1 — a threshold-watch report could land a full sample gap
  late.** When the watch is armed the probe sleeps to the next *sample* rather
  than the next report, clamped to whatever is left before the report is due so
  the report is not delayed. A guard meant for the "report just fired" case
  (`untilReport == 0`) tested `gap < WATCH_SAMPLE_MIN_MS` instead — which also
  fires for any remainder of 1..4999 ms, undoing the clamp on the line
  immediately above. The probe then slept a whole `cfg_sample_ms` instead of the
  short remainder, landing the report up to one sample gap late (60 s on a 60 s
  sample cadence) on **every cycle** where `cfg_interval % cfg_sample_ms` fell in
  that band — roughly one arbitrary interval/sample pairing in twelve. The hub's
  freshness windows (2.5× interval) absorb it, so nothing showed offline; the
  reporting cadence was simply not the one the operator set. The sleep
  arithmetic now has host-side coverage alongside the watch predicates: it
  decides both battery life and report punctuality and had none.
- **A busy hub buried its own log under waitress queue warnings.** Waitress logs
  a WARNING for every queued request while its worker pool is saturated, and
  saturation is a sustained condition — a 45-second burst produced **13,383 of
  them against 404 real hub lines**, a 33:1 flood describing successful
  backpressure (nothing failed in that run). The realistic trigger is twenty
  probes draining buffered readings at once after an outage, which is exactly
  when an operator is already anxious and reading their log. They also bypassed
  `logs/hub.log` entirely — waitress logs to its own top-level logger while the
  hub's handlers hang off the `hub` tree, so they printed to the console in a
  foreign format and never reached the file a customer is asked to send to
  support. Waitress now writes through the hub's own handlers, and the
  queue-depth stream is throttled to one notice per five minutes carrying a
  count of what it stood for. Every other waitress record passes untouched, so a
  real serving error is never hidden. Same treatment
  `probe_discovery._quiet_zeroconf_cache_race` already gives zeroconf.
- **Multi-site over plain HTTP to an off-site address said nothing.** Forwarding
  sends head office's **device token** — the credential that lets a caller write
  into its reading log — plus every reading, and over `http://` to somewhere off
  the local network that all crosses the wire in the clear.
  `docs/MULTI_SITE.md` has always said "use HTTPS in production, or a VPN", but
  the Settings form where a store manager actually types the address said
  nothing, and they have no reason to have read that file. Saving now warns —
  and only when it is genuinely a problem: `http://` to a LAN address is the
  ordinary deployment and exactly what the field's placeholder shows, and a
  Tailscale address is an encrypted overlay set up on purpose. Neither is
  flagged, because a warning that fires on the normal case trains people to
  ignore it.
- **`send_email` could raise instead of returning a reason.** Its contract is
  `(ok, reason)`, and `Notifier.dispatch` and the Settings "Send test" button
  both call it without a `try`. But the `EmailMessage` construction sat *outside*
  its own try block, and Python's email package refuses a header containing a
  line break — correctly; that is header injection — by raising `ValueError`. One
  malformed recipient in `config.json` therefore turned "Send test" into an
  unhandled callback error, and every real alert into a bare "notification
  dispatch error" in the log with nothing naming the field at fault. It now
  returns a reason that names it.
- **A power cut could make the audit log report itself as tampered with.** The
  truncation check rests on "the log is at least as far along as its anchor", and
  the entry was written before the anchor by *issue* order only — both sit in the
  page cache and the kernel may write them back either way round. An unclean
  shutdown that landed the anchor and lost the entry would report the audit trail
  as possibly truncated on the next start, permanently, having tampered with
  nothing. The entry is now fsynced before the anchor advances. Entries are
  written on config changes and exports, not per reading, so this costs nothing.
- **A spreadsheet export of a temperature-only probe carried two empty
  columns.** `export_friendly_csv` promises "unused humidity/VPD dropped", but
  the gate asked whether the *hub* held humidity anywhere, not whether *this
  export* did. So one grow probe in the building put a permanently blank
  `humidity_pct` and `vpd_kpa` on every other export — including the
  single-freezer file a restaurant hands an inspector, and any date range from
  before a grow probe was installed. The gate now takes the export's own
  filters. An unfiltered export is unchanged, and a hub with no humidity at all
  still produces the byte-identical file it always has.
- **Setting an alarm limit with notifications off said nothing.** Entering a
  min/max on the Devices page is the operator saying "tell me if this goes
  wrong", and the save confirmation is the moment they believe they are covered.
  With the notification master switch off nothing will ever reach them — the
  dashboard shows the breach, and the 2am freezer failure the product exists to
  catch is found in the morning. Nothing anywhere contradicted that belief: the
  Settings badge read "Off" in the same neutral grey as "Keep forever" and
  "Single site", which are perfectly fine defaults. Saving a limit with alerts
  off now says so in the confirmation (in amber, not a green tick over small
  print), and the Settings badge reads **"Limits set, alerts off"** in warning
  colour — but only once something actually has limits, because with nothing
  being watched, alerts being off is a neutral fact.
- **The gauge kept claiming everything was fine after the probe stopped
  reporting.** It is the largest element on the dashboard, and it drew a
  probe's last reading as a confident green bar — directly beside a "NO DATA"
  badge saying the opposite, and above per-probe cards that had correctly greyed
  themselves out. It now mutes and its caption reads "· last known"; the value
  stays, because the last known reading is the most useful thing the hub still
  has, it just must not be dressed as current.
- **The Max tile was painted alarm red for every reading.** `text-danger` was
  hard-coded in the markup *and* in the callback, so a Prep Room peaking at
  22.9 °C inside an 18–25 °C band sat in the KPI row looking like an incident.
  Red means "a limit was crossed" everywhere else on the page; a colour that
  fires unconditionally teaches an operator to ignore the one colour that must
  never be ignored. Both tiles now go red only when the extreme really did cross
  the limit of the probe it came from.
- **The overview's Average tile printed a word where a number goes.** A blended
  average across a −18 °C freezer and a 21 °C room is a number no probe is near,
  so the overview deliberately doesn't headline one — but it printed the word
  "Per-probe" in the big bold slot the other two tiles fill with a temperature,
  which reads as a failed render, in the part of the page people scan first. It
  is now an em-dash with the explanation underneath.
- **Diagnostics dropped every probe the moment they went quiet.** The table
  listed only what was freshly reporting or currently visible over mDNS, so a
  site going dark emptied it completely — "0 reporting · none discovered yet"
  above a blank space, on the page whose whole purpose is that a customer can
  copy it and send it to support. It was least informative exactly when
  something was wrong. Probes that have reported in the last week are now listed
  as offline with how long they have been silent, and the reporting/online counts
  are unchanged. The Name column also duplicated the Probe ID column exactly (it
  showed the mDNS-announced name, which the firmware sets equal to the id); it
  now shows the name the operator gave the probe, so a row says "Chest Freezer"
  rather than "Setpoint-4B71E0" twice.
- **The hub's device token could be sent off the LAN.** `api/routes.py` refuses a
  body-supplied hostname on the ingest path, and its comment says why: it "lands
  in the discovery registry, and the auto-provisioner then resolves it and POSTs
  the hub's device token to whatever it points at". That closed the ingest route
  in; the mDNS route it came from was left open. A `_temps-probe._tcp.local.`
  record's `server` field was taken verbatim and resolved with `getaddrinfo`,
  which falls through to unicast DNS for anything outside `.local` — so a record
  advertising `collector.example.net` resolved to a public address and received
  the token, which is write access to the reading log from anywhere. No attacker
  is needed either: an ISP resolver with wildcard NXDOMAIN hijacking answers every
  name, including a probe hostname that has momentarily stopped resolving over
  mDNS. Now two gates (`core/netaddr.py`): discovery drops a record whose host is
  outside `.local` (RFC 6762 §3) and drops an answer outside LAN ranges, and the
  provisioner re-checks the target immediately before sending — the address is
  re-resolved every cycle, so the check has to live where the secret is handed
  over as well. The LAN ranges are written out explicitly rather than using
  `ipaddress.is_private`, which calls RFC 5737 documentation space private and
  calls `100.64/10` — what Tailscale hands out — public. The gate also hands the
  *verified address* back to the caller rather than a yes/no, so the token goes
  to exactly what was checked: `provision_probe` resolved the name a second time
  at the point of sending, and two answers to one question is all a hostile mDNS
  responder needs — a LAN address while being checked, a public one a moment
  later.
- **A probe with a friendly mDNS name could never leave the Devices grid.** The
  discovery registry matched a `ServiceStateChange.Removed` event against
  `ProbeInfo.name` — which is the TXT `name` key, and PROTOCOL.md §3 defines that
  as "friendly name, else `probe_id`": a *human label*, equal to the id only by
  convention. The shipping firmware happens to set them equal
  (`g_instanceName = g_probeId`), so removal worked by coincidence. Give a probe
  the friendly name the protocol expressly allows and its departure matched
  nothing, so an unplugged probe stayed on the Devices grid and in the hub's
  probe total until the hourly prune eventually noticed it had gone quiet.
  Removal now compares the service instance label against a probe's *identities*
  — TXT `id`, hostname, registry key — with the display name kept only as a last
  resort. Matching whole identities instead of prefixes also makes the old
  "`Setpoint-9A` must not remove `Setpoint-9A3F2C`" hazard impossible rather than
  guarded against.
- **"Set up a new probe" claimed the probe was not there on machines that could
  not look.** The helper watches for the probe's `Setpoint-XXXXXX` setup network
  and reported "Setpoint-XXXXXX: not found — power the probe with no saved
  Wi-Fi…" whenever it saw nothing. But a hub with no way to scan returns exactly
  the same empty result as one that scanned and found nothing, and that is not a
  rare configuration: the hub is meant to live on an always-on mini-PC, which is
  usually wired; macOS 14.4 removed the `airport` binary the mac path shells out
  to; and Raspberry Pi OS Lite has neither `nmcli` nor `iwlist`. So a customer
  was sent off to power-cycle a probe that may well have been broadcasting the
  whole time, and never told the one thing that would have worked. The helper now
  separates "I cannot scan", "I scanned and saw no networks at all" (a wired
  machine) and "I scanned and your probe is not among them", and the first two
  say to join the setup network from a phone and open `http://192.168.4.1`.
  `POST /api/ingest` without `X-Probe-ID` (or a body `probe_id` of junk) answered
  `{"ok": true}` and filed the row under the empty string — which every UI
  surface skips by design, which "remove device" refuses to touch, and which the
  CSV export writes with a blank column. So an integrator who forgot the header
  watched the readings total climb while no probe ever appeared, with nothing
  anywhere saying why. The reading is still kept — a bad label is never a reason
  to lose a temperature — but it is now filed under the reserved id
  `unidentified`, which shows up as an ordinary probe that can be renamed or
  removed. PROTOCOL.md §2 and §6.4 also disagreed with each other about this (one
  said the hub rejects a malformed id, the other that it sanitizes and logs it
  anyway); §6.4 was right and §2 now says so.
- **A bulk ingest reported `rejected: 0` for a chunk it had partly thrown away.**
  `/api/ingest_csv`'s parser dropped JSON elements that were not objects, and CSV
  lines with fewer than four fields, before the counting loop ever saw them — so
  the reply under-reported. That last shape is exactly what a probe buffer
  truncated mid-append leaves behind, which is the one case where the number has
  to be true: a probe draining a corrupted backlog was told every line was fine.
  Both now count as `rejected`, as PROTOCOL.md §7 always said they did. Blank
  lines are padding and still don't count.
- **The Dashboard and the Devices grid gave opposite verdicts on the same
  probe.** Each derived probe condition independently. Given a probe that
  breached its limit and then stopped reporting, the Dashboard tested staleness
  first and drew a calm grey "● stale" — dropping the alarm entirely — while the
  Devices grid tested the breach first and drew a red "ALARM" with an hours-old
  temperature beside it and nothing saying it was old. One probe, one moment, a
  grey card on one page and a red one on the other, and neither told the whole
  truth about the state that matters most: out of range *and* out of contact.
  Both pages now read one shared verdict (`core.status.probe_state`) and report
  both facts — **ALARM · NO SIGNAL**. The same change stopped the Dashboard
  calling a probe with no limits set "● OK" in green; the Devices grid already
  refused to, and green on the page people leave open was the wrong reassurance
  about a probe nothing was checking.
- **Start.bat gave up on machines that had Python installed.** Three uses of
  `%errorlevel%` sat inside parenthesised blocks, where cmd.exe substitutes the
  value when it *parses* the block — so each test read the exit code from before
  the block ran. The `python3` and `python` fallbacks were therefore checking
  whether the *`py` launcher* probe had succeeded, and never ran. On any Windows
  box without the py launcher (a Microsoft Store or Anaconda install) the
  launcher printed "Python 3.9 or newer is required but was not found" and quit.
  The same file also emitted UTF-8 box-drawing characters with no `chcp`, which a
  default code-page-437 console renders as mojibake, and shipped with LF line
  endings, which cmd parses inconsistently in exactly the parenthesised blocks
  and `for /f` loops it is built from. It is now plain ASCII with CRLF (pinned by
  a new `.gitattributes`), every exit code is tested at run time, and a crash
  reports its code instead of closing the window.
- **A crash in Start.sh closed the window on its own error message.** `set -e`
  aborted the script the moment `app.py` exited non-zero, so the "Press Enter to
  exit" that existed to keep the failure on screen was unreachable in the one
  case it was for. Ctrl+C (130) still exits without asking for a keypress. The
  script also only *assigned* `HOST`/`PORT` rather than exporting them, so the
  port printed in the banner and the port the hub bound were two independent
  defaults that agreed by coincidence; both are now exported, and a test pins
  them to `app.py`'s.
- **"Remove device" left the removed probe holding an alarm forever.** The alert
  monitor copies each probe's state forward every cycle and only revises probes
  that reported — deliberate, since that is what keeps a breach held while a
  probe is silent. But a deleted probe never reports again, so `HELD` went on
  publishing `high` for a device that no longer existed, and re-adding the same
  id started it already in breach. State is now dropped on the monitor's hourly
  sweep for probes with **no rows at all**; a merely silent probe keeps its open
  incident.
- **Multi-site forwarding respected a row limit but not the receiver's byte
  limit.** `/api/ingest_csv` refuses a body over 64 KB, and a row count cannot
  honour a byte budget: 500 readings — the shipped default — encode to ~62 KB of
  the 63.5 KB budget with a bare temperature, and to ~92 KB once a grow probe
  adds humidity and battery. So the default already 413s forever for the probes
  that report most, and the configured maximum of 1000 rows (124 KB) 413s for
  everyone. Nothing retried its way out: the same bytes were rebuilt every cycle,
  so forwarding simply stopped. Batches are now trimmed to prefixes that fit
  before the round trip is spent, by binary search (the obvious pop-and-re-encode
  loop measured 480 encodes and ~0.5 s of CPU per cycle at a 1000-row batch, on
  the forwarder thread, forever). Trimming takes from the tail only — both
  cursors advance to the last id accepted, so dropping from anywhere else would
  step past records that were never sent — and readings give way before events,
  which are the record an auditor asks for. A size-trimmed batch still counts as
  full for the fast drain, since what it dropped is still waiting.
- **The Wi-Fi scan behind "Set up a new probe" now only runs while that section
  is open.** It shells out to `netsh`/`nmcli` every few seconds, and previously
  started on any visit to the Settings page — opening Settings to change a
  retention day is not consent to scan the airwaves. `SSIDWatcher` also survives
  being stopped and started again: it re-used one `Event` that `start()` never
  cleared, so every restart spawned a thread that exited before its first scan,
  leaving a watcher that looked running and reported nothing. Each thread now
  owns its own event (so a retired one can't be revived by a later `clear()`,
  and a new one can't race a stale flag), and `stop()` interrupts the sleep
  rather than letting it run out — previously up to a full interval of further
  scanning — and drops the last sighting, which is not current once scanning has
  stopped.
- **Changing the MQTT base topic no longer silently kills every Home Assistant
  sensor.** Saving Integrations restarts the publisher, but the set of
  already-announced probes survived the restart, so nothing re-announced. Home
  Assistant learns a probe's state topic from a *retained* discovery message, so
  it stayed subscribed to the old topic while the hub published to the new one —
  every existing sensor going stale, until the hub was restarted. `stop()` now
  clears the announce set (and the cap flag), so the next reading re-announces
  each probe against the topics actually in effect.
- **A multi-site backlog now drains fast at any configured batch size.** The
  forwarder's "a full batch means there is more waiting, don't sleep" check
  compared against the 500-row `DEFAULT_BATCH` constant instead of the batch it
  had actually used, so with `upstream.batch` set below 500 a full batch could
  never reach it. A store hub back from an outage caught up at one batch per
  interval — hours instead of minutes. Both sites now derive the size from one
  `batch_size()` helper.
- **Diagnostics lists probes known only from readings.** A deep-sleep probe
  keeps its radio off between readings and is never mDNS-discovered. The summary
  counted it under "reporting" while the table below omitted it, so the snapshot
  read "3 reporting" above a table of one with no way to tell which two were
  missing. `/api/probes` has always appended them; the snapshot now applies the
  same overlay.
- **A legacy database no longer re-runs its schema migration on every startup.**
  When a store holds genuinely-distinct readings that share a probe id and
  instant (pre-millisecond timestamps), the unique index cannot be built — and
  the failed attempt re-ran a full-table `GROUP BY` dedupe plus a failed index
  build on every single open, i.e. on precisely the oldest and largest
  databases. The verdict is now recorded in `meta` and honoured thereafter.

### Internal

- **`probe_discovery.py` covered, 35% → 88%.** It was the least-tested module in
  the repo and the only one that parses bytes it did not produce, arriving from
  any host on the LAN, before they reach the Devices grid, `/api/probes`,
  Diagnostics and the auto-provisioner — which then POSTs the hub's device token
  to what it finds. Writing the tests is what surfaced the friendly-name removal
  bug above. Now pinned: TXT parsing (including a value that is not UTF-8, which
  must cost that key and not the probe), the two-identities merge, removal, the
  zeroconf calling-convention shim, prune/forget/last-seen, the registry ceiling
  against an mDNS flood, browser lifecycle, and the resolver's bounded wait and
  its promise not to touch the process-wide socket timeout. Also pinned: the
  asyncio filter that quiets zeroconf's own cache-expiry race does *not* swallow
  a `KeyError` from the hub's own code, or anything that is not that race.
- **`core/probes.py`: one definition of how to read a probe record.** The
  discovery registry holds `ProbeInfo` dataclasses *and* plain dicts, so
  `/metrics`, `/api/probes`, the Diagnostics snapshot, the Devices grid and the
  auto-provisioner each carried their own attribute-or-key dance — and one had
  already drifted, which is how `setpoint_probes_total` came to equal
  `setpoint_probes_online` on every scrape. The five copies are now one helper,
  and the test that covers it calls the real function instead of re-implementing
  it (which is why that regression survived its own test).
- Removed `core.applog.setup_logging`, dead since loggers moved to the `hub`
  tree: nothing called it, and anything that had would have split the log across
  a second file.

- **The chart range selector could silence a live alert.** The alert banner and
  the "needs attention" gauge share one latest-per-probe scan, and that scan was
  scoped to the *selected chart range* rather than the probe-presence window.
  Both consumers already gate each row on `_probe_fresh_window` — the
  interval-aware "is this probe live?" test — so the query window was redundant
  filtering that turned a view control into an alerting control: a probe on a 2 h
  cadence whose last reading was 90 minutes old is still fresh (18000 s window)
  and its card read "▲ HIGH", but selecting "Last Hour" dropped its row before
  the freshness gate ran, so the banner showed nothing and the gauge picked a
  different probe. Now scanned over `PROBE_PRESENCE_WINDOW`, which the per-probe
  cards already query every tick, so it costs nothing new.
- **Hub health is now judged on the same clock as the probes.** `/api/health`,
  `/api/diagnostics` and `setpoint_healthy` all used `HealthState.snapshot()`'s
  flat 120 s freshness bound, even though the parameter exists precisely so
  callers "monitoring slow-cadence probes" can pass an interval-aware one. A
  single probe on a 600 s cadence therefore reported `healthy:false` for 480 of
  every 600 seconds — the Diagnostics page rendering "Needs attention" directly
  above its own table listing that probe online, and `setpoint_healthy` flapping
  1→0→1 on every scrape. New `core.status.hub_health_window` widens the bound to
  the slowest probe's own fresh window (same shape as `probe_prune_window`), so
  a deep-sleep deployment stops crying wolf while a fast fleet is unaffected.
- **A fresh install no longer logs an ERROR traceback on every dashboard
  refresh.** The empty-store case raised `ValueError("no data")` into the
  catch-all handler, which logs with `log.exception`, so a hub that simply had
  not been used yet wrote a stack trace roughly four times a minute per open tab
  into the same rotating log that real field incidents must be diagnosable from.
  It now returns the no-data state directly, shared with the failure handler so
  the two cannot drift in arity.
- **The `/metrics` latest-reading registry is now bounded.** `core.metrics.LATEST`
  had no ceiling and was fed straight from the `X-Probe-ID` header, so every
  distinct id added both a permanent entry and a permanent exposition series:
  20 000 ids produced a 2.9 MB scrape response, making it a memory leak and a
  scrape-amplification vector at once. Capped at 512 tracked probes, evicting the
  stalest entry — eviction rather than refusal, because this map is "current
  temperature per probe" and a real sensor must be able to displace noise.

- **`setpoint_probes_total` counted only reporting probes, silently disarming the
  "a probe went quiet" alert.** `/metrics` read each discovered probe's id with
  `getattr(p, "probe_id", None)`, but the discovery registry stores `ProbeInfo`
  dataclasses, which have no `probe_id` field — the id lives in
  `.properties["id"]`. The expression returned `None` for every probe, so the
  discovered set was always empty and `probes_total` equalled `probes_online` on
  every scrape. `probes_total - probes_online > 0` — the one condition the two
  gauges exist to express, and the obvious Grafana alert for a silent freezer
  sensor — could therefore never fire, and `/metrics` disagreed with the
  dashboard, which counts discovered probes correctly. Now uses the same
  properties-first accessor as `api/routes.py` and `core/diagnostics.py`.
- **Non-ASCII credentials returned HTTP 500 instead of 401, and could lock an
  operator out of the dashboard permanently.** `hmac.compare_digest` accepts
  `str` only when *both* operands are ASCII-only and raises `TypeError`
  otherwise. Both operands can be non-ASCII here: the configured side
  (`UI_PASSWORD` / `ui_auth.password` / `SERVER_TOKEN`, coerced to `str` by the
  schema but never constrained to ASCII) and the client-supplied side (request
  data). An operator whose password contained an accented character got a 500 on
  the dashboard, every download and every Dash callback, with no way in through
  the UI; separately, any unauthenticated client could turn its own 401 into a
  500 by sending a non-ASCII password or `X-Token`. Comparison now happens on
  UTF-8 bytes via `core.secret_compare.constant_time_eq`, which keeps the
  constant-time property and fails closed.

- **A mistyped per-probe setting no longer looks applied when it isn't.**
  `probe_intervals`, `probe_resolutions` and `calibration_offsets` were checked
  only for being objects; their inner values were never coerced, unlike
  `alert_thresholds`. Nothing crashed — every consumer already defends itself and
  falls back — which was the problem: the misconfiguration was silent, while the
  Devices card rendered the *raw* config value. Hand-editing an interval to
  `"30s"` produced a card reading "Interval: 30s s" while the probe carried on at
  the global interval. All three are now coerced at load with a warning (values
  clamped to their valid range, unparseable entries dropped), so the stored
  config, the value actually in effect, and the value displayed agree. Quoted
  numbers (`"1800"`) are accepted silently — only a real value change warns.

- **An alert that never reached anyone is no longer invisible.** Notifications
  could be lost two ways and neither surfaced: a channel failure (SMTP down,
  webhook 500, bad credentials) and a dropped event when the dispatch queue
  filled. Both only wrote a log line, while the dashboard still showed the breach
  and the event log still recorded it — so an undelivered alert looked exactly
  like a delivered one, which in an alerting product is the worst possible
  failure mode. The channel case was the easy one to miss: `Notifier.dispatch`
  reports a dead channel by *returning* `ok=False` rather than raising (each
  channel catches its own errors), so the existing `try/except` around it saw a
  clean run. `HEALTH` now counts `notify_failures` and `notify_dropped`
  separately — one is a broken channel, the other is back-pressure — and both
  appear in `GET /api/health` and `GET /api/diagnostics` beside the
  is-it-configured flags, because whether alerts are *configured* is a different
  question from whether they are *arriving*.
- **`/api/diagnostics` now reports the `unauthorized` counter** it already
  claimed to. `HealthState` documented it as "surfaced in /api/health and
  /api/diagnostics"; only the former was true. A probe holding a stale device
  token 401s on every wake and is otherwise indistinguishable from a probe whose
  hub is down.

- **An unknown-probe-id flood can no longer litter Home Assistant permanently.**
  MQTT discovery announced one entity per `(probe, metric)` pair and remembered
  them in an unbounded set. A probe id arrives as an `X-Probe-ID` header on the
  open-by-default ingest API and sanitizes to 32 characters of `[A-Za-z0-9_-]`,
  so its cardinality is effectively unlimited — the exposure `probe_discovery`
  already bounds with `_MAX_PROBES`. Here it was worse than a memory leak:
  discovery entities publish with `retain=True`, and a retained message outlives
  the hub, a broker restart and the flood itself, so the phantom entities had to
  be cleared by hand. Announcements are now capped (1536 pairs = 512 probes × 3
  metrics, far past any real fleet) and the cap logs once. Readings keep
  publishing past the cap — capping discovery must never cost a reading — and an
  already-announced probe is never re-announced, since evicting to make room
  would turn a bounded set into an unbounded stream of retained publishes.

- **A wall clock that jumps forward can no longer delete the entire reading
  history.** `purge_older_than` deletes on `epoch < now - retention_days`, so it
  trusts the system clock. A clock reading far in the *past* was always harmless
  (the cutoff goes negative and matches nothing), but a clock reading far in the
  *future* — a bad NTP answer, a VM resumed from a stale snapshot, a mistyped
  date — put the cutoff beyond every stored reading, so the next hourly retention
  sweep silently deleted everything, with no undo. `delete_future_readings`
  already guarded the mirror case; this side had no guard at all. Retention now
  declines to run when the cutoff is at or past the newest reading held, on the
  principle that trimming the tail must never empty the store. The one legitimate
  case this also declines — a hub offline for longer than its retention window —
  resolves itself as soon as probes report again and the cutoff falls back behind
  the newest epoch.

### Added

- **The Devices page now says when a settings change will actually reach the
  probe.** Config is delivered by the probe *pulling* it off an `/api/ingest`
  reply, so on a long deep-sleep interval it lands on the next check-in, not on
  Save — and because the hub cannot query a sleeping probe, it can never confirm
  delivery. Previously the modal simply closed and the "will be applied on its
  next check-in" note went only to the log, leaving no way to tell a slow
  delivery from a broken one. Saving now reports the probe's reporting interval
  and the time by which it should be running the new settings (a *full* interval
  out — the probe may have checked in moments before Save), and says outright
  that the hub cannot confirm until then. Probes reporting faster than once a
  minute get a plain confirmation instead, since an ETA there is noise.
- **Saving with `auto_provision` off now warns instead of failing silently.**
  That switch makes the hub omit `config` from every ingest reply, so a change
  saved against a sleeping probe reaches it *never* rather than late. The
  behaviour is deliberate ("don't manage my probes") but had no UI or manual
  coverage at all, so the save looked successful. The Devices page now says the
  setting was stored on the hub but will not be sent, and points at the switch.

- **Firmware v2.8.1 — bulk backlog drain + cold-boot rejoin (from the held 2.8.0
  work), plus long-sleep robustness.** `bufferFlush()` now drains an offline
  backlog to `POST /api/ingest_csv` in ~100-reading chunks instead of one POST per
  reading, so a cold-soak backlog uploads in seconds with far less radio-on time
  (transparent per-reading fallback on an older hub). A probe with saved
  credentials now retries its network for a 60 s grace on cold boot and continues
  **offline** rather than flipping to its own setup AP on a brief miss — the
  "recharge hosts an AP and looks broken" bug — with an NVS-backed escape hatch
  that opens the setup portal after three consecutive failed cold boots so a
  moved or re-SSID'd probe is never stranded.

### Changed

- **Probe settings now reach a deep-sleeping probe.** Configuration was delivered
  only by the hub *pushing* to the probe's `POST /provision`, but a sleeping probe
  serves HTTP for ~3 s every Nth wake — on a long interval that is a fraction of a
  percent of the time, so a change made in the dashboard could sit undelivered
  indefinitely (the probe kept reporting on its old interval). `POST /api/ingest`
  now returns the hub's desired `config` (`interval_ms`, `resolution_bits`) and the
  firmware applies and persists it, so settings arrive on the probe's *own* next
  post — every wake, at no extra radio cost. Both paths derive the value from one
  shared helper so push and pull cannot disagree; `server_url`/`token` stay
  push-only so a reply can never re-point a probe at another server. Backward
  compatible in both directions.
- **Disturbance-burst threshold scales with the reporting interval.** The 1 °C
  trigger is calibrated against wakes a few seconds apart, but it compares against
  the *previous wake* — so at a 15-minute cadence a fridge's normal compressor
  swing crossed it routinely, firing a 20 s radio-on burst on ordinary operation.
  The threshold now scales with wake spacing (capped at 4 °C) and bursting is
  disabled entirely above a 5-minute interval, where a burst can no longer catch
  the event that triggered it.
- **NTP drift resync is time-based, not wake-count-based.** Resyncing every 30
  *wakes* meant 2.5 minutes at a 5 s interval but 7.5 hours at 15 minutes and 30
  hours at an hourly cadence — least often exactly when RTC drift is worst (the
  board has no 32.768 kHz crystal and runs its RC oscillator cold in a freezer).
  It now resyncs after 30 wakes **or** ~6 h elapsed, whichever comes first.
- **Discovery pruning scales with the slowest probe's interval.** The flat 1 h
  eviction would drop a probe reporting at or beyond hourly *between* posts,
  removing it from the Devices grid and churning the provisioner's bookkeeping.
- **The alert engine judges freshness per probe.** `_readings()` used the flat
  `alert_freshness_sec` (600 s) while every other surface used
  `probe_fresh_window`, so a probe on a 15-minute interval flickered in and out of
  the alert engine (absent ~⅓ of ticks; ~⅚ at hourly) while the dashboard
  correctly showed it online. Breach detection still worked — a fresh post is
  always evaluated — but presence-dependent behaviour (cooldown re-notification
  timing, HELD publication) was choppy. Both now use the same rule.

### Fixed

- **DST fall-back no longer loses (or scrambles) an hour of readings.** Readings
  are stored as local-naive strings, but the epoch was re-derived from that
  string — and during the repeated hour two UTC instants an hour apart share one
  wall time. They collided on `UNIQUE(probe_id, epoch)`, so one was discarded,
  and everything that sorts by epoch (chart, exports, rate-of-change window)
  interleaved the whole hour. The probe stamps in UTC, so the unambiguous instant
  is now carried past the local conversion instead of being recomputed from it.
  Verified: both readings stored, same displayed wall time, epochs 3600 s apart,
  true chronological order preserved.
- **A truncated buffer line is no longer stored as a phantom probe.** A line cut
  mid-write by a dying battery still splits into four fields — the cut lands in
  the probe id — so it was accepted as a real reading filed under a mangled id
  like `Setpo`. A probe only ever drains its own buffer, so a row whose id
  disagrees with the request's `X-Probe-ID` is now rejected as corrupt.
- **A breach that happened entirely during an outage is no longer invisible.**
  The alert engine only evaluates each probe's *latest* reading, so a freezer
  that thawed while the hub was down — the single most important thing not to
  miss — was stored by the backlog drain and then never surfaced, because by
  reconnect time the probe read normally again. The drain now records the worst
  excursion per probe in the event log, stamped at the time it actually
  occurred, so it appears in Recent events and the history. Deliberately not
  dispatched as a live notification: it is old news by definition.
- **Firmware v2.8.2 — a probe with no clock no longer throws its readings away.**
  `nowIso()` returns nothing until NTP has synced, and `bufferAppend()`
  early-returned on an empty stamp — so on a **LAN with no internet**, the
  deployment this product is explicitly sold for, the offline buffer never
  engaged and every reading taken while the hub was unreachable was lost
  outright. Clockless readings are now buffered with an empty stamp and
  receipt-stamped by the hub on drain, 1 ms apart, so the values survive. Such a
  backlog carries drain-time chronology rather than measurement-time; a probe
  that has a clock is unaffected, since the RTC checkpoint keeps stamping
  through an outage exactly as before. (The live path already handled this — the
  hub stamped a timestamp-less POST — so only buffered readings were affected.)
- **Bulk backlog drain lost humidity, VPD and battery.** The live path extracts
  them but `/api/ingest_csv` never did, so a grow probe (SHT4x) reconnecting
  after an outage came back temperature-only — a hole in exactly the data that
  niche buys the product for. `bulk_insert` now carries the optional telemetry
  (the 4-tuple form still works for the legacy-CSV migration).
- **The two discovery pruners disagreed.** The alert monitor's hourly sweep still
  used the flat `probe_prune_after_sec`, so it would evict a deep-sleeping probe
  that the provisioner's scaled window was protecting. Both now call one shared
  `core.status.probe_prune_window`.
- **The ingest config reply looked up overrides with the raw `X-Probe-ID`.** The
  reading is stored under the *sanitized* id and the Devices page writes
  overrides under it, so a probe id needing sanitization silently missed its
  per-probe interval/resolution.
- **Silent data loss draining a backlog from a clock-skewed probe.** A probe
  whose clock ran ahead during the outage that filled its buffer replays rows
  stamped in the future. `normalize_payload` clamped each row to its own "now",
  so a 100-row chunk collapsed onto the same millisecond and
  `UNIQUE(probe_id, epoch)` discarded all but one or two — while `/api/ingest_csv`
  still answered `200`, so the probe advanced its checkpoint and deleted the
  buffer it had just lost. Measured: 100 rows in, **2 stored**; a 720-row hour-long
  backlog lost 92 readings. Future-dated bulk rows are now receipt-stamped 1 ms
  apart (the mechanism already used for timestamp-less rows), the count is
  returned as `restamped` and logged, so the condition is no longer invisible.
- **An unsynced hub clock no longer overwrites good probe timestamps.** The
  ingest future-clamp trusted the hub's wall clock unconditionally — the same
  clock the DB layer already refuses to trust. On a hub that boots before NTP
  lands (a Pi with no RTC), every correctly-stamped reading looked "far in the
  future" and was replaced with the hub's wrong time. The clamp now applies only
  above the shared trust floor, which is defined once in `core.storage` and
  imported by `core.db` so the two guards cannot drift.
- **A body-supplied `host` on `/api/ingest` could exfiltrate the device token.**
  It was written straight into the discovery registry, and the auto-provisioner
  then resolved it and POSTed the hub's token to that address — bypassing the
  SSRF guard on `/api/provision`, and letting a poisoned entry hijack a real
  probe's id. Only the transport-observed peer address is trusted now (matching
  what the bulk path already did).
- **One bad per-probe config value no longer takes the fleet down.**
  `probe_intervals`/`probe_resolutions` were unvalidated, and
  `desired_probe_config` is now on the live ingest path — so `inf` (which
  `json` parses from `1e400`) raised `OverflowError` on **every** reading from
  **every** probe and aborted each provisioning cycle. All conversions are now
  bounded and total.
- **The hub no longer provisions probes with an unreachable loopback URL.** When
  LAN-IP autodetection fails (no default route, DHCP blip, bridged container)
  the base can be `127.0.0.1`; pushing it pointed every probe at *itself*, and
  `_pushed` recorded the config as delivered so it never self-corrected. The
  cycle is now skipped with a warning naming `PUBLIC_BASE`.
- **`auto_provision: false` is honoured by the new config-pull.** The flag gated
  only the background pusher, so the ingest reply kept overwriting a
  hand-configured probe with the hub's global interval, with no way to opt out.
- **A stale device token is now diagnosable.** A probe holding an old token 401'd
  on every wake and buffered forever, while the hub recorded nothing at all and
  the Devices grid just showed it offline. 401s are counted, surfaced in
  `/api/health` and `/api/diagnostics`, and logged (rate-limited) with the probe id.
- **Startup no longer wipes the entire history when the clock is wrong.**
  `delete_future_readings()` runs on every hub start and deleted rows stamped
  after `now + tolerance`. On hub hardware without a battery-backed RTC (a
  Raspberry Pi) that boots to 1970/a stale date before NTP syncs, that low clock
  made the **whole legitimate history** look "future" and removed it
  irreversibly. The purge is now skipped when the wall clock is implausibly early
  (before a 2025-01-01 trust floor); a trustworthy clock still purges genuine
  future-stamped rows.
- **A webhook URL's bearer token no longer leaks on a delivery error.**
  requests/urllib3 render the host and the token-bearing path+query separately in
  their exception text, so the whole-URL `str(e).replace(url, …)` scrub matched
  nothing and the secret reached both the hub log and the Settings "Test" result.
  The failure message is now built from the exception type and host only.
- **Config secrets are no longer briefly world-readable.** The atomic-save temp
  file was created with a plain `open()` (0o644 under the default umask) while
  holding SMTP/webhook/provisioning secrets, and an already-loose `config.json`
  was never re-secured on load. The temp file is now created `0o600` and an
  existing file is `chmod`ed on load.
- **CSV/Excel exports dropped the final second's sub-second rows.** `app.py`
  carried its *own* copy of `_parse_date_epoch` that still truncated the
  `?to=` end-of-day bound to `…59`, so `/download/temperature_log.csv` disagreed
  with `/api/readings` for the same date range. The duplicate is gone; both paths
  now share one implementation.
- **Focus mode no longer over-decimates a quiet probe's chart.** `window_df`
  sized its downsample stride from the **global** all-probe row count, so
  drilling into a low-rate probe beside a chatty one drew its line from as few as
  1–2 points while the UI truthfully reported "Showing 20". `window_df` now takes
  a `probe_id` (stride and scan both scoped to the focused probe), and the
  "of *N*" denominator is scoped to match.
- **A malformed JSON body returns 400 instead of 500.** A top-level JSON
  array/number/string reached `data.get(...)` before any dict guard on
  `/api/ingest`, `/api/provision` and the token check, raising an unhandled
  `AttributeError`. A shared `_json_body()` helper now coerces a non-object body
  so it takes the normal validation path.
- **`/api/health` stays a 200 health surface when the DB is busy.** Its
  `db.count()` was unguarded, so a locked/unreadable SQLite file turned the very
  endpoint monitors poll into a 500; it now degrades to `readings: null`.
- **Website: mobile navigation and horizontal scrolling.** The hamburger menu was
  dead on *every* page — `about`, `services` and `replacement-parts` never had
  one (their headers simply hid links at ≤720 px), and on `index` the base
  `display:none` was declared *after* the media-query override, so equal
  specificity plus source order kept the button hidden at every width. Mobile
  visitors could only navigate from the footer. Separately, the footer link row
  could not wrap, giving `index`/`about`/`services` 87–183 px of horizontal
  scroll on a phone, and the contact email overflowed a 320 px viewport. All four
  pages now pass with no horizontal scroll at 320 px and 390 px.
- **`?to=YYYY-MM-DD` sub-second rows: the fix now actually reaches the query.**
  The end-of-day bound was built as a fractional epoch (`…59.999999`) but the DB
  layer cast it back with `int()` before the `epoch <= bound` compare, truncating
  it to `…59` and re-dropping `23:59:59.001–.999` on the `to` date — in both the
  JSON read API and every CSV/xlsx export. The bound is now passed through as a
  float.
- **MQTT no longer silently dies on a `null`/blank topic or a stringy flag.** A
  hand-edited `mqtt.base_topic`/`discovery_prefix` of `null` (or `""`) used to
  become `None` and crash every publish on `None.rstrip()` — a connected-but-mute
  integration — because the key-missing default never applied to a present-null
  value; it now falls back to the documented default. A string
  `discovery_enabled: "false"` is likewise honored as off instead of read as
  truthy by `bool()`.
- **A huge integer in config.json no longer crashes the hub on load.** `float()`
  of an integer literal larger than a C double (~1e308) raises `OverflowError`,
  which is not a `ValueError` and escaped `normalize_config`'s "never raises"
  contract; it is now caught and the field falls back to its default with a
  warning.
- **A garbage Fahrenheit value can no longer bypass the ingest range gate.** When
  a payload sent both units, only Celsius was range-checked, so a bad
  `temperature_f` (e.g. C=25, F=9999) reached the DB and poisoned the column,
  stats and exports. The Fahrenheit band (`-76..302 F`) is now checked too.
- **12-hour clock mode: consistent AM/PM at every zoom.** The graph's finest
  (sub-second) tick tier was left in 24-hour `%H:%M:%S`, so a zoomed-in
  high-cadence chart mixed `14:30:05.1` ticks with `2:30:05 PM` hovers.
- **Ingest is now idempotent.** A `UNIQUE(probe_id, epoch)` index backs the
  readings table and both write paths use `INSERT OR IGNORE`, so a re-sent
  reading — a dropped ACK on a bulk `/api/ingest_csv` flush re-POSTs a whole
  chunk — can no longer create duplicate rows that inflate COUNT/AVG/min-max and
  exports. Timestamp-less bulk rows are receipt-stamped 1 ms apart so a chunk
  isn't collapsed to one row. A pre-existing DB is de-duplicated in place when
  the index is built, collapsing **only byte-identical** rows — two distinct
  readings that merely share a whole-second epoch (old whole-second stamping of a
  sub-1 s cadence) are preserved, falling back to a non-unique index rather than
  being silently deleted.
- **Rate-of-change alert now uses the true window-old sample.** `_check_rate`
  took `fetch_readings(window)[0]`, but that caps to the most-recent N rows
  before reversing, so on a high-cadence probe (e.g. 0.5 s over a 60 min window)
  the "past" sample was only ~N-old — understating the delta and missing slow
  rate alerts. A new index-backed `db.oldest_temp_c_in_window()` fetches the real
  oldest reading in the window.
- **`?to=YYYY-MM-DD` range now includes the final second's sub-second rows.** The
  end bound was `…59` with `epoch <= bound`, which dropped `23:59:59.001–.999` on
  the `to` date for readings carrying fractional (millisecond) epochs.
- **Auto-provisioner no longer leaks bookkeeping or gets stuck.** Its
  `_provisioned`/`_pushed` maps are pruned when discovery evicts a probe (they
  grew unbounded on a churning/spoofed fleet), and it re-verifies a probe's
  `/status` every N cycles even when config is unchanged — so a probe that
  silently lost its NVS config but keeps advertising mDNS is re-provisioned
  instead of staying unconfigured until a hub restart.

### Added

- **Offline flap damping for weak-Wi-Fi probes.** A probe on a spotty link (e.g.
  freezer Wi-Fi through a metal door) that drops, lands one reading, then drops
  again used to fire an *offline* + *back online* pair every cycle — the exact
  "flapping (15×)" churn the Recent-events feed already coalesced, but which the
  notifications did not. Connectivity now gets the same damping the temperature
  path has always had: the drop is reported once, but the **back-online** alert is
  *held* until the probe has reported steadily for a confirmation window, so a
  brief blip no longer clears the outage. The eventual single back-online message
  notes when the link was unstable and how many times it dropped. A new
  **Confirm back-online after** setting (`notifications.flap_grace_sec`) controls
  it: blank/`null` = auto (self-tunes to each probe's own offline window), a number
  pins the hold in minutes, and `0` disables damping (the previous
  report-on-first-reading behaviour). Pure-function core in
  `core.alerts.evaluate_offline` (new `recover_hold_sec`), wired through the alert
  monitor, config schema and Settings page.
- **Bulk backlog drain — `POST /api/ingest_csv`.** A probe recovering from an
  outage (weak freezer Wi-Fi, hub down) can have thousands of readings buffered
  to flash; draining them one-HTTP-POST-per-reading is slow and burns radio time
  on a battery probe. The hub now accepts a whole chunk in one request — CSV (the
  probe's on-flash buffer format) or JSON, ≤ 1000 rows — validated exactly like
  `/api/ingest` and written in a single transaction (`db.bulk_insert`). Invalid
  rows are skipped, not fatal; the response reports `accepted`/`rejected`. This
  endpoint was already specified in `PROTOCOL.md` (§7) but never implemented;
  §5.1 now documents the body formats. The single-reading `/api/ingest` is
  unchanged, so existing firmware keeps working — the matching firmware change
  (chunked buffer flush + HTTP keep-alive) ships separately.

## [2.6.2] - 2026-07-23

### Added

- **Illustrated DIY-kit assembly guide.** `docs/ASSEMBLY.md` is rewritten from the
  stale ESP32-WROOM/GPIO2 hand-wired build into a photo-illustrated, start-to-finish
  guide for the actual **C3 SuperMini carrier kit** (solder → flash → Wi-Fi → live
  dashboard), with the real-build gotchas baked in (switch-OFF flashing, BOOT/RST
  download mode, JST notch orientation, pre-power meter checks, cell spec). Photos
  are referenced from `docs/images/assembly/` with a commit-checklist manifest.
- **Flashing troubleshooting for a blank C3/S3 that keeps re-connecting.** The web
  flasher page and the DIY build guide now document the download-mode fix — **hold
  BOOT, tap RST, release BOOT** — for a new board whose USB port drops / keeps
  re-enumerating instead of holding a stable connection for flashing.

### Fixed

- **Stale firmware version on the flasher page and build guide.** The web flasher
  and `web/guide.html` displayed "firmware v2.4.1" while the shipping firmware (and
  `flash/manifest.json`) is **2.7.0**. Both display strings now read 2.7.0.
- **DIY-kit flashing instructions had the power switch backwards.** The web
  flasher page and the DIY build guide told buyers to flash with the power
  switch ON. On the kit the switch only gates the battery→ESP32-C3 path, so the
  SuperMini's own USB-C powers the board for flashing regardless of the switch —
  and leaving it ON lets USB power back-feed the cell through the TP4056. The
  flashing steps now say **switch OFF**, the power-check step explains USB powers
  the board directly, and the troubleshooting table no longer blames a "No LED on
  USB" symptom on the switch (it can't cut USB power) — with a new
  battery-specific row where an off switch is the real cause.

### Changed

- **De-noised the dashboard's "Recent events" feed.** Connectivity churn
  (online/offline) is now **coalesced per probe** into a single row that reports
  the probe's current state and, when it has dropped more than once, a
  "flapping (N×)" count — so a probe on a weak link (Wi-Fi from inside a metal
  fridge, say) no longer buries the alerts that matter under a wall of
  online/offline entries. Threshold and rate events (high/low/recovery/rate)
  still render individually, newest first — and are fetched in their own
  kind-filtered query, so even a probe flapping hundreds of times can't push a
  genuine breach out of the feed's fetch window. Every row now carries a
  relative timestamp ("just now", "22m ago", "3h ago", "2d ago") instead of a
  bare wall-clock time, so at a glance you see *how recent* an event is rather
  than having to read a timestamp.

## [2.6.1] - 2026-07-22

### Fixed

- **Temperature History zoom reset on every refresh.** The earlier `uirevision`
  fix preserved a user's zoom on the time (x) axis, but the temperature (y) axis
  still snapped back to the default on each 5-second auto-refresh — so a
  box-zoom, which pans both axes, appeared to reset. The cause was an explicit
  `yaxis.range` recomputed from the window's live min/max on every tick: Plotly
  treats a *changed* programmatic range as an override and discards the user's
  zoom even while `uirevision` is unchanged. The auto-fit range is now carried
  by an invisible anchor trace that feeds Plotly's autorange instead of pinning
  the axis, so the default (un-zoomed) view still tracks the data while a zoom
  now persists across refreshes until you change the time range, unit, or focus
  (or double-click to reset).

## [2.6.0] - 2026-07-22

### Added

- **Spreadsheet-friendly data exports.** The dashboard's Export dialog now
  offers three formats instead of one raw CSV, so the exported file is ready to
  work with for people who expect an Excel-style document:
  - **Excel-friendly CSV** (the new default): `date` and `time` are split into
    separate columns in the hub's local wall clock — so Excel/Sheets parse each
    as a real date/time value and sort, filter and pivot natively, instead of
    importing an ISO `...T...`-with-milliseconds string as inert text. The
    probe's friendly name is shown alongside its raw id, the unused
    `humidity_pct`/`vpd_kpa` columns are dropped, and the file is written
    UTF-8-with-BOM so Excel opens degree signs and accented names correctly.
    The exact machine-independent `timestamp_utc` is still included.
  - **Excel workbook (`.xlsx`)**: a native workbook with true date/time/number
    cells, a frozen header row and filter dropdowns — double-click and it's
    already typed and ready. Streams via openpyxl's write-only mode so a long
    log doesn't buffer in memory, and refuses (with a clear message to narrow
    the range) rather than silently truncate past Excel's ~1,048,576-row limit.
  - **Raw CSV**: the previous canonical/system-of-record format (full ISO-8601
    timestamps, every column) is unchanged and still available for scripts and
    re-import. Existing `/download/temperature_log.csv` links keep working — the
    format is selected with a new optional `?format=excel|xlsx|raw` parameter
    (default `raw`), so nothing that bookmarked the old URL changes.
- **openpyxl** added as an optional dependency (imported lazily; a missing
  install only disables the `.xlsx` download — both CSV exports need no extra
  packages).

## [2.5.0] - 2026-07-21

The "better product" release: everything from a full six-lens review of the
codebase (bugs, firmware, ease of use, visual design, performance, product
gaps), with every finding verified against source before implementation.

### Fixed

- **Offline alert spam for deep-sleep probes (the #1 review bug).** The alert
  engine still used one flat global `offline_after_sec` while every screen used
  the interval-aware freshness window — so a 10-minute battery freezer probe
  flapped offline→online on every wake (~288 spurious notifications/day) while
  the UI showed it green. The notifier now judges each probe by its own
  `probe_fresh_window`, and `DEMO-` probes never alert.
- **Honest hysteresis.** A breach held open by the deadband no longer emails
  numerically false "above the threshold" reminders while the dashboard shows
  green OK: reminder text now says the reading has not yet cleared the limit by
  the deadband, and the probe card shows an amber "recovering" badge (via the
  new shared `core.alerts.HELD` registry) until the alert actually clears.
- **Power-outage lockout (firmware).** A cold boot with saved Wi-Fi credentials
  but no reachable network (router still booting after an outage) sat in the
  captive portal forever, logging nothing at ~100 mA. The portal now times out
  (180 s) and falls through to offline logging with periodic reconnects.
- **Offline-buffer data loss (firmware).** A brownout between deleting the
  flushed buffer file and zeroing its NVS offset could silently delete the NEXT
  outage's backlog. The offset is now zeroed first, and an implausible offset
  re-flushes from the start instead of deleting.
- **Provisioner fought the operator.** The auto-provisioner froze the global
  interval at boot and actively re-provisioned the fleet back to the stale value
  after `interval_sec` was changed; it now reads config live each cycle.
- **Diagnostics probe rows** now use the same reporting-freshness overlay as
  every other surface (no more red "offline" rows for healthy deep-sleep probes
  on the exact page users copy for support).
- **Health flag un-latched:** one transient write failure no longer marks the
  hub "Needs attention" forever — only a failure newer than the last successful
  write counts.
- **Thresholds in your unit.** The Devices edit modal displayed °C fields even
  when the dashboard showed °F — "Max 40" meant 104 °F and the alert never
  fired. Thresholds and calibration now display and accept the active unit
  (correct delta math for the offset) and store °C canonically.

### Added

- **Event history.** Breaches, recoveries, offline/online transitions and rate
  alerts are recorded to a new SQLite `events` table (even when notifications
  are off) and shown in a "Recent events" card on the dashboard — the product
  can finally answer "did anything go out of range while I was away?".
- **Rate-of-change alerts.** "Rose more than X °C within Y minutes" (Settings →
  Alerts, 0 = off) catches a failing freezer or open door in minutes, hours
  before the static threshold trips.
- **Daily summary email.** One email a day (configurable hour) with each
  probe's 24 h min/avg/max — doubles as a dead-man's switch proving the email
  pipeline works.
- **Battery telemetry.** Ingest accepts `battery_pct`/`battery_v` (3.0–4.2 V
  mapped); shown on probe and Devices cards ("Batt NN%", amber < 20) and in the
  JSON API. Firmware wiring for the standard divider can follow.
- **Threshold bands on the chart.** Focused (or single-probe) history draws the
  min/max limits and shades the out-of-range regions.
- **MQTT from the UI.** New Settings → Integrations card (host/port/user/
  password/base topic/HA discovery, blank password keeps saved) applies live —
  no more config.json hand-editing for the flagship integration; Help updated.
- **Install to home screen (PWA).** Web-app manifest + meta so the dashboard
  adds to a phone home screen and launches full-screen.
- **Firmware v2.7.0** also gains: non-blocking NTP with backoff (an
  internet-less LAN no longer freezes the probe 8 s/min and disables
  buffering), millisecond-accurate clock restore across deep sleep with a
  proper resync counter, buffer-flush checkpointing every 10 lines with a ~20 s
  per-wake budget, and a full-interval sleep after a disturbance burst.

### Changed

- **Performance at scale:** `latest_per_probe` rewritten from an O(window)
  scan to per-probe index seeks; the dashboard skips full rebuilds when nothing
  changed (per-client render signature, 15 s staleness bucket); per-tick
  duplicate window scans folded; `reporting_probe_ids` bounded to a 7-day
  lookback; demo detection is an O(log N) index probe; the provisioner skips
  sleeping probes and redundant status checks.
- **Visual polish:** status badges regain per-state colors (and LOW no longer
  falls through to magenta); low-temperature alerts render cool blue instead of
  amber; small-caption contrast raised to WCAG AA; native controls render dark
  (`color-scheme`); KPI values share one scale; the LIVE badge uses a CSS
  pulsing dot; OS emoji removed from UI chrome; gauge fits its card.
- **Setup & docs truthfulness:** Setup Helper names the real per-unit
  "Setpoint-XXXXXX" network (and tells you which one it found); the user manual
  no longer promises humidity/VPD alert settings that don't exist, uses correct
  click-paths, documents wrong-Wi-Fi recovery and the new features; PROTOCOL.md
  documents the battery ingest fields.

## [2.4.6] - 2026-07-21

### Fixed

- **History graph dropped a probe's readings after it was flashed to millisecond
  firmware.** Firmware ≥ 2.5.0 stamps readings with millisecond precision, so a
  just-flashed probe's 24 h window mixes pre-flash whole-second
  (`…T03:00:00`) and post-flash millisecond (`…T03:00:00.500`) timestamps. The
  dashboard parsed the timestamp column with pandas' default `to_datetime`, which
  infers a single format from the first row and silently coerces the other
  precision to `NaT` — so the probe kept recording (its per-probe stats and count
  were correct) but its points **vanished from the graph**. Both timestamp parses
  now use `format="ISO8601"`, which accepts either precision. Regression test in
  `tests/test_dashboard_freshness.py`.

## [2.4.5] - 2026-07-21

### Added

- **Per-probe sensor resolution, set from the dashboard (firmware v2.6.0 + hub).**
  The Devices → ✏️ Edit modal now has a **Sensor Resolution** dropdown (9–12 bit;
  0.5 °C → 0.0625 °C steps). Like the per-probe interval, it's stored as an
  override (`probe_resolutions` in config, falling back to a global
  `resolution_bits` default of 11), pushed to the probe via `/provision`, and
  persisted to the probe's NVS. The firmware applies it live and keeps the
  conversion-wait in step, and echoes `resolution_bits` in `/whoami` and
  `/status` so the auto-provisioner only re-pushes when it actually differs.
  `provision_probe(... resolution_bits=...)`, `POST /api/provision`, and the
  auto-provisioner all carry the field; it's omitted when unset, so old
  firmware/callers are unaffected. Higher resolution resolves finer detail (the
  0.5 °C stair-steps seen in a freezer door-open capture); it does not change the
  sensor's ±0.5 °C absolute accuracy. Covered by new cases in
  `tests/test_provisioning.py` and `tests/test_config_schema.py`.

## [2.4.4] - 2026-07-21

### Added

- **Firmware v2.5.1 — adaptive "disturbance burst" for freezers / hard-to-reach
  spots.** In deep-sleep mode the probe is asleep between wakes, so a brief event
  (a freezer door opening) and the short connectivity window it opens could be
  slept through. Now, when a wake reading jumps more than `BURST_DELTA_C` (1 °C
  default) from the previous one — carried across sleep in RTC memory — the probe
  treats it as a disturbance: it stays awake, keeps Wi-Fi up, samples every
  second and flushes the offline buffer hard for ~20 s before returning to deep
  sleep, so the event and any backlog reach the hub while they can. It also
  retries the Wi-Fi association during the burst (a closed freezer is an RF box;
  the door opening may be the first real chance to connect). Bounded by a
  consecutive-burst cap so a door held open (or a slow thaw) can't hold the probe
  awake and flatten the battery. This catches an event only if a scheduled wake
  lands during it, so it helps most at short/moderate intervals; true
  wake-on-temperature would need an analog sensor + comparator on a wake pin (a
  hardware revision — the DS18B20 has no interrupt output). Set
  `BURST_ON_DISTURBANCE false` to disable.

### Changed

- **Firmware v2.5.1 — battery & data-quality tuning.** (1) Per-wake Wi-Fi
  reconnect budget cut from 15 s to 8 s with a **backoff**: after repeated
  failures a probe that can't associate (deep in a freezer, hub down) only
  attempts a connect every Nth wake — radio off on the others — instead of
  burning up to 15 s of radio every wake; the single biggest drain in poor RF.
  (2) The 3 s HTTP provisioning window is now served on the first few wakes and
  then periodically, not on every deep-sleep wake. (3) DS18B20 resolution raised
  **9-bit → 11-bit** (0.5 °C → 0.125 °C steps, ~375 ms conversion), resolving
  gradual changes that previously quantised into visible stair-steps while still
  fitting the 500 ms minimum interval (12-bit's 750 ms would not). This changes
  the quantisation step, not the sensor's ±0.5 °C absolute accuracy. (4) A failed
  (`DEVICE_DISCONNECTED_C`) sensor read is retried up to twice within the wake
  before being treated as a fault, so a transient 1-Wire glitch no longer leaves
  a gap in the log.
- **Millisecond timestamps end-to-end (firmware v2.5.1 + hub).** Readings are now
  stamped to millisecond precision (`2026-07-21T00:42:04.500Z`), which the hub
  preserves through ingest, storage (a fractional epoch, backward-compatible with
  existing integer rows), the CSV export's `timestamp_utc` column, and the JSON
  API. A high-rate cadence (down to the firmware's 500 ms floor) stays
  distinguishable instead of collapsing multiple readings onto one whole-second
  stamp — as happened when logging a freezer door-open transient at 0.5 s. A
  probe that only sends whole seconds is unchanged (no spurious `.000`). Covered
  by new cases in `tests/test_storage.py` and `tests/test_db.py`.

## [2.4.3] - 2026-07-21

### Added

- **Read your data as JSON — live, without the CSV download.** A new read-only,
  unauthenticated JSON API (the JSON twin of the CSV export and `/metrics`):
  - `GET /api/readings/latest` — the current reading of every probe
    (`probe_id`, `timestamp`, `temperature_c/_f`, `humidity_pct`, `vpd_kpa`);
    the 90% case for polling live values into another process.
  - `GET /api/readings?window=24h&probe=<id>&from=&to=&limit=N` — historical
    readings with the same filters the CSV download accepts, plus an exact
    `stats` block over the full window. The row list is capped (newest kept) so
    a months-long store can't return an unbounded body.
  Covered by `tests/test_api_readings.py`. The Help page now has a short
  **"Connect it to other tools"** section pointing at this API, the Prometheus
  `/metrics` scrape endpoint, and MQTT/Home Assistant — all of which already
  existed but were undiscoverable in the UI.
- **`/metrics`: `setpoint_probes_online` gauge** — probes reporting within their
  freshness window, matching the dashboard's "Connected Probes", so a Grafana
  alert on it agrees with the built-in UI.

### Fixed

- **"Online/connected" now means the same thing on every surface.** The
  dashboard/Diagnostics counted a probe connected via an interval-aware freshness
  window, but `/api/probes`, `/api/health` and `/metrics` still used a flat 60 s
  mDNS timeout — so a deep-sleep battery probe read "connected" on-screen yet
  `online: false` (and dropped from the online count) via the API between wakes,
  making a Grafana panel flap on a probe the UI said was fine. All surfaces now
  derive "reporting" from one shared helper (`core.status.reporting_probe_ids`),
  and a DB-only (never-mDNS-seen) probe is listed by `/api/probes` too.
- **`/metrics` ghost series after "Remove device".** The Prometheus registry
  never evicted a removed probe, so `/metrics` kept serving its frozen last
  temperature (and an ever-climbing `last_reading_age`) forever — a probe the
  dashboard, Devices grid and Diagnostics had already dropped. Removing a device
  (and clearing demo data) now evicts it from the registry.
- **Misleading blended "Average Temperature" on the multi-probe overview.** With
  two or more probes the headline average blended, e.g., a freezer and a room
  into one number no probe is near. The overview now points that tile to the
  per-probe breakdown below (which already existed) and keeps global Min/Max as
  the coldest/hottest reading anywhere. Single-probe and focus mode are
  unchanged — there the average is meaningful.

### Changed

- **Devices grid labels status in words, not colour alone** ("Online · 5 min
  ago" / "Offline · 12 min ago"), fixing a colour-only (WCAG 1.4.1) state that
  made an online and an offline probe read identically, and matching Diagnostics
  and the dashboard cards.
- **Settings — alert fields dim when alerts are off.** With the master "Enable
  alerts" switch off, the alert-configuration block is now dimmed and
  non-interactive with an inline note, so the form can't look configured while
  nothing will fire.

## [2.4.2] - 2026-07-20

### Fixed

- **Dashboard freshness consistency (review follow-up).** A code review found
  that "is this probe fresh?" was decided several different ways, so the same
  probe could read differently on one screen. Unified on a single shared helper
  (`core.status.probe_fresh_window`) and fixed the fallout:
  the **alert banner** and the "needs attention" gauge no longer fire for a probe
  that breached once and then went silent (they now agree with its "● stale"
  card); **focus mode's "Last Update"** tracks the focused probe instead of the
  hub-wide newest reading (a silent focused probe no longer reads "Just now");
  the **Diagnostics** "reporting" count and the **Devices** grid's online colour
  now use that same interval/offline-aware window as the dashboard; the
  **humidity/VPD** cards use the same 7-day presence window as every other
  per-probe view; the **Logging Status** KPI is amber (not success-green) when
  logging is OFF; and the "all" range skips a full-table `COUNT(*)` on every tick.
  Devices edit-modal fixes: an inverted **min > max** threshold is now corrected
  instead of alerting on every reading, and saving a name/threshold-only change
  no longer writes a spurious per-probe interval override or re-provisions the
  probe. Covered by `tests/test_dashboard_freshness.py`.
- **Hub dashboard (v2.4.1):** removed a duplicated clock-format callback block
  that registered a second pair of callbacks on the same outputs
  (`clock-format-store.data` and the 24h/12h button outlines). With no
  `allow_duplicate`, Dash's browser renderer rejects the *entire* callback graph
  on page load, so the dashboard drew its static shell but **no callback ever
  fired** — the page-content stayed empty and the footer was stuck on
  "Status: starting…". Server-side registration accepted both callbacks and all
  unit tests passed, so only a full callback-graph load surfaced it; a new
  regression test (`tests/test_callback_graph.py`) now fails on any duplicate
  callback output.
- **Firmware (v2.4.1):** a deep-sleep probe that wakes during a Wi-Fi/router
  outage now restores its clock from the RTC *before* the Wi-Fi check, so it
  buffers readings to LittleFS instead of dropping them for want of a
  timestamp. Previously the RTC restore was gated behind the Wi-Fi-connected
  branch, so readings taken while offline were silently lost — the exact case
  the offline buffer exists for.
- **Hub:** `/api/diagnostics` no longer exposes the absolute database path to
  unauthenticated LAN callers; the onboarding `curl` example uses POST (ingest
  is POST-only and rejected the prior GET with 405).

### Changed
- **Release/CI housekeeping.** Bumped the GitHub Actions that were pinned to the
  now-deprecated Node 20 runtime (`actions/checkout` v4→v5, `actions/setup-python`
  v5→v6, `softprops/action-gh-release` v2→v3) so workflow runs stop emitting
  deprecation warnings. The `release` workflow now auto-populates each Release's
  notes from `packaging/RELEASE_NOTES.md` (download table + the "first launch
  shows a security prompt" guidance for the unsigned installers).
- **Rebranded the product to "Setpoint, by Datum Labs."** The device, hub app, and integration
  surfaces now carry the new name end to end: the setup Wi-Fi / probe id is `Setpoint-XXXXXX`
  (was `TempSensor-XXXXXX`), the mDNS hub instance is "Setpoint Hub", the app data directory is
  `Setpoint`, the Prometheus metrics are namespaced `setpoint_*` (were `tempsensor_*`), the MQTT
  default base topic is `setpoint` and Home Assistant discovery ids are `setpoint_*`, the log file
  is `setpoint.log`, and the macOS/Windows installers ship as **Setpoint**. Internal build
  identifiers (the `temperature-hub` onedir artifact, the `temperature_hub.spec` filename, and the
  `TEMPSENSOR_FW_VERSION`/`_PROTO` firmware macros) are unchanged. **Re-flash probes** so they
  advertise the new id; **Prometheus/Grafana dashboards and MQTT subscriptions must update to the
  `setpoint*` names.** A new `docs/ACTION_PLAN.md` captures the revenue-first go-to-market plan.

### Added
- **One-click installers + a release pipeline.** A new `release` GitHub Actions workflow builds a
  **Windows `.exe` installer** (Inno Setup), a **macOS `.dmg`** (`.app` bundle), and a **Linux
  `.tar.gz`** on native runners and attaches them to a GitHub Release when you push a `v*` tag. The
  installers are **code-signed and (on macOS) notarized** when signing secrets are configured, and
  build unsigned otherwise. The frozen app now stores its data in a **per-user directory**
  (`%LOCALAPPDATA%` / `~/Library/Application Support` / `~/.local/share`) so it runs from a read-only
  install location without admin rights, and **opens the dashboard in the browser on launch**. See
  `docs/INSTALL.md` (users) and `docs/RELEASE_SIGNING.md` (maintainers).
- **Smarter CSV export.** "Download CSV" now exports exactly what you're viewing — the selected time
  range and, in focus mode, just that probe. A new **Export** dialog adds a custom **date range** and
  **per-probe** selection. Backed by `Database.export_csv(probe_id=…, start_epoch=…, end_epoch=…)` and
  `?probe=`/`?from=`/`?to=` query params on the download route.
- **Unambiguous timestamps in exports.** Every CSV row now carries a `timestamp_utc` column derived
  from the reading's epoch, alongside the existing local `timestamp`, so exported data stays correct
  across daylight-saving changes and different machines. The export dialog names the hub's timezone.
- **System health panel (Diagnostics).** An at-a-glance health card — status (Healthy / Needs
  attention), uptime, readings in the last 24 h, last write, rows written this run, rejected ingests,
  write failures, and free disk — with a low-disk warning. So you can trust the logger is recording.
- **Try it with demo data.** The first-run empty state has a **▶ Load demo data** button that seeds a
  day of realistic sample readings (clearly-labelled `Demo …` probes) so a new user can explore the
  dashboard, charts, export and per-probe views before any hardware arrives; a banner offers one-click
  **Clear demo data**, which never touches real probes.
- **Remove a device.** The Devices edit dialog now has a **🗑 Remove device** button (with a
  confirmation) that deletes all of a probe's readings and its saved name / thresholds / calibration /
  interval, and forgets it from discovery — so accumulated test devices can be cleared. New
  `Database.delete_probe()` and `ProbeDiscovery.forget_probe()`. A still-powered probe will reappear on
  its next reading (the dialog says so) — power it off first to remove it for good.
- **Dashboard focus mode.** A "🔍 Viewing" selector lets you drill from the all-probes overview into a
  single probe: the gauge, history graph and Min/Avg/Max statistics then show only that probe (with its
  own threshold band and auto-ranged axis), and the per-probe overview grids collapse to just that one.
  A many-probe hub can now be read either at a glance or one probe at a time, instead of an
  ever-growing wall of cards. New `Database.window_stats(probe_id=…)`; the graph palette grew to 12
  colours so more probes stay distinct.

### Changed
- **Settings page is clearer.** The alerts card is split into **When to alert** and **Where to send
  alerts**; the Email and Webhook fields stay collapsed until you enable that channel (progressive
  disclosure); the retention field shows a live "0 = keep everything, forever" / "⚠ older readings are
  permanently deleted" note and reads in plain-language sections; and there's a direct link to the
  Devices page where per-probe alert limits are actually set.
- **Form styling polish (Settings, edit dialogs).** Inputs and selects were bright white against the
  dark UI; they are now dark-themed to match, section headers are brightened with a divider line, and
  the hover "lift" is limited to the interactive probe cards instead of every card.

### Added
- **Per-probe Min / Avg / Max statistics** — when 2+ probes have data, the dashboard adds a per-probe
  statistics breakdown below the overall row, so a mixed deployment isn't collapsed into one
  meaningless aggregate (an "average" across a −18 °C freezer and a 22 °C room is nonsense). A
  single-probe deployment is unchanged — the global row already tells the whole story. Backed by a new
  `Database.stats_per_probe()` query.
- **Per-probe status cards on the dashboard** — one card per probe showing its current temperature and
  an at-a-glance **OK / HIGH / LOW / stale** state (colour-coded, with a freshness age), so a
  multi-probe deployment is legible at a glance instead of a single gauge showing whichever probe
  reported last.
- **The main gauge is now useful** — it focuses on the probe that needs attention (the worst active
  threshold breach, else the latest reading), draws **coloured threshold zones** (blue below min, green
  in the safe band, red above max), colours the bar by state, and auto-ranges the axis around the band
  — so a −18 °C freezer and a 32 °C office each read sensibly instead of on a fixed 0–100 scale.

### Changed
- **The Devices page now lists probes known only from ingest** (not just mDNS-discovered ones), so a
  **deep-sleep battery probe** — whose radio is off between readings and is never mDNS-visible — still
  appears and can be renamed / thresholded / calibrated.
- **Dashboard styling is now fully offline** — the Bootstrap/CYBORG theme is vendored locally
  (`assets/bootstrap-cyborg.min.css`) instead of loaded from a CDN, so the hub renders correctly with
  no internet (offline homelabs, air-gapped networks) — matching the local-first promise. Dash already
  serves its own JS/Plotly locally, so the hub now needs zero external hosts.
- **"Connected Probes" counts probes that are actually reporting** (from the readings DB within the
  online window), not just mDNS-discovered ones — so a **deep-sleep battery probe** (radio off between
  readings, never mDNS-visible) is correctly counted while it is posting.

### Fixed
- **Dashboard freshness no longer flickers deep-sleep probes offline.** The "Connected Probes" count and
  the per-probe **stale** badge used a fixed 60 s online window, so a battery probe that wakes every few
  minutes read as offline between wakes even while healthily reporting. The window is now the larger of
  the online timeout, the alert monitor's `offline_after_sec` (default 5 min — so the dashboard and the
  offline **alerts** now agree), and ~2.5× the probe's configured reporting interval. A typical
  deep-sleep probe now stays "connected" between wakes with no per-probe configuration.
- **Browser flasher now targets the ESP32-C3 we actually ship on.** `flash/manifest.json` declared
  `chipFamily: "ESP32"` (classic), so ESP Web Tools would **refuse to flash** a C3 board. It now
  declares **`ESP32-C3`**, `build_merged_bin.sh` compiles for the C3 with the **No-OTA (2MB APP / 2MB
  SPIFFS)** partition scheme and prefers the core's own chip-correct merged image, and the
  manual-flash / `factory_flash.py` FQBN defaults follow suit. (Browser flashing writes the whole
  image over USB serial, so the no-OTA scheme flashes fine — OTA only concerns wireless updates.)
- **Rebranded to `TempSensor`** — the hub, the probe, the firmware, the Prometheus metric prefix
  (`tempsensor_*`), the MQTT base topic, and all documentation now use **TempSensor** in place of
  ThermaHub/ThermaProbe. The probe's setup-AP SSID and probe ID become **`TempSensor-<HEX6>`**.
  **Probes must be reflashed** to pick up the new identity (they will report under a new ID after
  reflashing).
- **Setup Wi-Fi is now an open network** — the probe's first-time setup SoftAP (`TempSensor-<HEX6>`)
  no longer uses a WPA2 password, so setup is one-tap. The AP only exists during provisioning and is
  torn down once the probe joins the home Wi-Fi; the `[label]` serial line now prints `ap_pass=none`,
  and the label/QC docs drop the Wi-Fi-password field. A per-unit WPA2 key can be reintroduced for
  higher-security deployments (see `SECURITY.md`).

### Added
- **Browser-based firmware flashing** (`flash/`) — an [ESP Web Tools](https://esphome.github.io/esp-web-tools/)
  page that flashes the TempSensor firmware onto an ESP32-C3 from Chrome/Edge with no toolchain,
  plus `build_merged_bin.sh` to produce the merged image and a README for hosting it (GitHub
  Pages). The lowest-friction on-ramp for kit/BYO-hardware hobbyists. (Binary is generated, not
  committed; needs a hardware bench build.)
- **Hobbyist go-to-market ladder** in `docs/LAUNCH.md` — a lowest-barrier path (software/BYO →
  kits → assembled+SDoC → B2B), tied to the browser-flash on-ramp.
- **`docs/TINDIE_LISTING.md`** — a ready-to-paste Tindie listing (title, summary, tags, kit/assembled
  price options, Markdown description, shipping, photo order) with a pre-publish checklist covering
  Tindie's exclusivity clause and the FCC-for-assembled caveat.

### Changed
- `docs/LAUNCH.md`: noted Tindie's web-exclusivity (pick one paid channel for the probe) and pointed
  the kit/direct-sell steps at `TINDIE_LISTING.md`.
- Corrected the README **Humidity & VPD** section to the shipped reality: the hub computes VPD
  from any probe that reports humidity, but the SHT4x probe *firmware build* and humidity/VPD
  *alert thresholds* are not yet implemented (temperature-only alerting for now).
- `docs/LAUNCH.md`: the deep-sleep **battery** capability now ships in the firmware, so it's a
  packaging option rather than a future architecture change; refreshed the release checklist.

### Security
- **Ingest now bounds `probe_id`** — sanitized to `[A-Za-z0-9_-]`, capped at 32
  chars, before it reaches the database, CSV export, or an MQTT topic. A real
  TempSensor (`TempSensor-<HEX6>`) is unaffected; a buggy/malicious LAN client
  can no longer store an arbitrary value. (Guard restored after the v2.4.0 merge.)
- **CSV export is formula-injection-safe** — a cell beginning with `= + - @`
  (or tab/CR) is prefixed with a single quote so a spreadsheet treats it as text,
  not a formula. Defence-in-depth for the free-form export columns.

## [2.4.0] - 2026-07-11

The reconciled "ready to sell" release. It unifies two lines of development: the
SQLite data layer, battery firmware, diagnostics, alert-reliability and packaging
work, and the homelab integrations, humidity/VPD grow variant, tamper-evident audit
trail, optional dashboard login, and the go-to-market / compliance / manufacturing
documentation suite.

### Added
- **Alert hysteresis / deadband** (`alert_hysteresis_c`, default 0.5 °C). Once a
  probe is in breach it must move back *inside* its limit by this margin before the
  alert clears, so a noisy sensor sitting on a threshold no longer flaps
  high → recovery → high and spam-notifies. Entering a breach still uses the raw
  threshold; set it to 0 for the previous behaviour. Pure, unit-tested logic in
  `core.alerts`.
- **Battery / deep-sleep firmware mode.** The TempSensor can run in a low-power
  **deep-sleep** cycle for long life on a rechargeable lithium battery, in addition
  to the always-on (USB) mode. Probes **NTS-sync** their clock and **buffer readings
  offline**, flushing the queue to the hub on reconnect so a brief hub outage or
  Wi-Fi drop loses no data.
- **Prometheus `/metrics` endpoint** — per-probe temperature (plus humidity/VPD)
  gauges and health counters, for scraping into Grafana. Toggle via `metrics.enabled`.
- **MQTT publishing with Home Assistant auto-discovery** — optional `mqtt` config
  block, off by default; each probe appears automatically as a Home Assistant sensor.
- **Humidity + VPD support (grow variant)** — an optional `-D SENSOR_SHT4x` firmware
  build reads an SHT4x temperature+humidity sensor over I2C and adds an optional
  `humidity_pct` field to ingest (backward-compatible, still protocol v1). The hub
  computes **VPD** (vapour pressure deficit) via the Tetens formula with an optional
  `settings.vpd_leaf_offset_c` leaf offset, shows Humidity + VPD on the dashboard,
  exposes `tempsensor_probe_humidity_percent` / `tempsensor_probe_vpd_kpa` Prometheus
  gauges, publishes separate humidity/VPD MQTT/Home Assistant sensors, and evaluates
  `humidity_min/max` and `vpd_min/max` per-probe thresholds.
- **Docker / headless deployment** — `Dockerfile`, `docker-compose.yml`, and a
  `CONFIG_FILE` env override so the hub runs on a NAS/server with a persistent volume.
- **Optional dashboard login** — HTTP Basic auth on the dashboard + CSV download for
  shared office/lab LANs (`ui_auth` config or `UI_USERNAME`/`UI_PASSWORD`), off by
  default; `/api/*`, `/metrics`, and the operational endpoints are exempt.
- **Tamper-evident audit trail** — a hash-chained, append-only log of config changes
  and data exports (`logs/audit.log`), with an integrity check at
  `GET /api/audit/verify`. A B2B/procurement differentiator and a foundation for any
  future regulated (Part 11 / Annex 11) path.
- **Go-to-market, compliance & manufacturing documentation suite** under `docs/`:
  `GO_TO_MARKET.md`, `COMPLIANCE.md` (FCC/CE path, calibration tiers, sellable B2B
  segments), `LAUNCH.md`, `LISTING.md`, `BOM.md`, `ASSEMBLY.md`, `QC_CHECKLIST.md`,
  `LABEL_TEMPLATE.md`, `USER_MANUAL.md`, `EULA.md`, `WARRANTY.md`, and `RETURNS.md`,
  plus developer docs `CONTRIBUTING.md` and `TESTING.md`.

### Changed
- **Store listing** (`docs/LISTING.md`) rewritten as a ready-to-paste,
  homelab/server-room-first listing for the lead product (always-on USB DS18B20
  probe): honest spec table (accuracy vs resolution), can't-be-bricked/local
  positioning, homelab-stack integrations, photo shot list, and FAQ — reviewed
  against the compliance honesty rules.

### Fixed
- **Alert threshold of 0 was silently ignored on the dashboard.** The dashboard alert
  banner used a truthiness check (`if min_threshold`), so a valid `min: 0`
  (freezer/greenhouse) never triggered the banner — even though the server-side
  notifier (which uses `is not None`) still emailed/webhooked it. A single shared
  `threshold_breach()` helper now backs both the dashboard and the notifier so they
  can't diverge again; unit-tested including the 0-bound case.

### Security
- **Recursive secret redaction from `GET /api/config`.** Nested secrets — including
  the notification **webhook URL** (a bearer secret) and `smtp_password` — are now
  redacted, and the webhook URL is no longer seeded into the Settings page. The
  dashboard is open by default, so any LAN device could otherwise read them.
- **Firmware: per-unit unique, WPA2-protected setup AP.** The deep-sleep firmware's
  setup network was previously **open and shared one SSID** across all units. Each unit
  now brings up a unique setup AP (SSID == its probe id) protected by a **per-unit 64-bit
  random** WPA2 key, generated once at first boot and stored in NVS (printed on the serial
  `[label]` line for the factory tool). `firmware/factory_flash.py` captures the id + key
  from serial for the unit label. *(Needs a real Arduino build + flash + bench validation.)*
- **Firmware: probe identity rebranded to `TempSensor-<HEX6>`** (6 hex, sensor-ROM-derived
  with a MAC fallback, persisted in NVS) so a manufacturing batch won't collide.
- Security review of the release: hub core auth verified sound (no injection, auth
  bypass, path traversal, or unsafe deserialization).
- Expanded `SECURITY.md` into the merged threat model + hardening roadmap (token-gated
  mutating endpoints, recursive redaction, `ui_auth`, audit trail, the unauthenticated
  operational endpoints, and the open setup-AP and default-open `/provision` firmware
  items).

## [2.3.0] - Professional polish: diagnostics, onboarding & robustness

### Added
- **Diagnostics page** (top nav) and a secret-free `GET /api/diagnostics` endpoint:
  hub version, LAN URL, readings stored, database size, newest reading, retention,
  per-probe online/offline, and which notification channels are enabled — with a
  one-click **copy** for support. Channels report on/off only; hosts, URLs, passwords,
  and tokens are never included.
- **First-run onboarding.** The dashboard shows a step-by-step "waiting for your first
  reading…" card until data arrives, then hides itself; the Devices empty state now
  guides setup instead of a bare "no probes" message.
- **Live footer status** reflecting real hub state (N probes online / offline / idle /
  "waiting for first probe") instead of a hardcoded "Status: Ready", driven by pure,
  tested `core.status.hub_status`.
- **Config validation** (`core/config_schema.py`): a hand-edited or partial
  `config.json` is coerced to safe types/ranges on load, with each correction logged —
  a bad file can no longer crash the hub.
- Repo hygiene: `CONTRIBUTING.md`, `SECURITY.md`, GitHub issue/PR templates, and README
  status badges.
- A rewritten **Help** modal organised around what customers do (get online, name &
  calibrate, alerts, data & backup, troubleshooting) instead of an API endpoint list.

### Changed
- All service/UI `print()` calls now use the logging framework (`hub.<area>` loggers).
  In the packaged no-console build, `print()` output was lost — crash diagnostics now
  reach the rotating log file.

## [2.2.1] - Stable probe identity (no more duplicate cards)

### Fixed
- **A single probe could appear twice on the Devices page.** The firmware derived the
  probe id from the DS18B20 ROM code when that read succeeded (`TempProbe-XXXX`) but
  fell back to the ESP32 chip id when it failed on a cold boot (`TempSensor-XXXX`).
  Because the probe re-runs `setup()` on every deep-sleep wake, one physical device
  could report two identities and show as two cards (same IP). Fixed on both ends:
  - **Firmware (root cause, requires reflash):** the probe id is now derived once —
    retrying the ROM read so the first id is the good ROM-based one — then persisted to
    NVS and reused on every boot, so a later failed read can never flip the identity.
    Firmware bumped to **v1.6.0**.
  - **Hub (defensive, no reflash needed):** `list_probes()` now collapses entries that
    share a LAN IP to the single most recently-seen one, so a device shows as one card
    and is counted once in `/api/health`. Pure, unit-tested logic
    (`probe_discovery.dedupe_probes_by_ip`).

## [2.2.0] - Offline-probe alerts & standalone packaging

### Added
- **Offline / back-online notifications.** The alert monitor now flags a probe that
  stops reporting for longer than `offline_after_sec` (default 5 min) and notifies
  again when it resumes — essential for unattended monitoring, where a dead probe is as
  bad as an out-of-range one. Pure, unit-tested logic (`core/alerts.evaluate_offline`).
- The first monitor cycle seeds connectivity state silently, so a hub restart never
  emits a burst of "offline" for probes that were already quiet.
- Settings → Notifications: "Alert when a probe goes offline" toggle and an
  "Offline after (minutes)" field.
- **Standalone packaging** (`packaging/`): a PyInstaller spec + build scripts produce a
  single executable so customers run the hub without installing Python, plus a systemd
  unit and Windows/macOS service instructions. The app is now frozen-aware —
  `config.json`, the database, and logs are written next to the executable (overridable
  with `DATA_DIR`), while bundled assets/config load from the packaged resources.

## [2.1.0] - Notifications, calibration, retention & backups

### Added
- **Threshold notifications** that run server-side on a background thread
  (`alert_monitor.py`), so alerts fire even when no browser is open. Channels:
  **email (SMTP)** and **webhook** (Slack-compatible `text` field + structured JSON for
  Zapier/IFTTT/custom). Per-probe min/max thresholds with a `default` fallback, a
  configurable reminder cooldown, and optional "back to normal" recovery notices. Alert
  logic is a pure, unit-tested state machine (`core/alerts.py`) that only emits on
  transitions/cooldowns — never one message per poll.
- **Per-probe calibration offset** (`calibration_offsets`), applied at ingest so the
  stored value is the corrected temperature (DS18B20s vary ~±0.5 °C). Editable from the
  Devices → Edit Probe modal.
- **Data retention** (`retention_days`): readings older than N days are purged
  automatically (hourly), keeping disk bounded. 0 = keep forever.
- **One-click database backup** (`/download/backup.db`) — a consistent SQLite snapshot.
- A **Settings UI** to configure notifications and retention without editing JSON, with
  a "Send test" button.
- Rotating file logging (`core/logging_setup.py`, `logs/hub.log`) replacing ad-hoc
  prints in the startup/serving path.

### Fixed
- `latest_per_probe` now breaks epoch ties by insertion id, so "latest" is
  deterministic when two readings land in the same second.

## [2.0.0] - 2026-07-06

First public release. 1.0 was never shipped — it was an internal prototype used to
prove out the DS18B20-over-Wi-Fi idea and is not documented here. 2.0.0 is a full
productization of that prototype into a local-first, no-cloud appliance a non-technical
customer can plug in and run, built on a proper SQLite data layer.

### Added
- **Branding / config system** — everything ships from `config.json` (seeded on first
  run from `config.example.json`): product/brand name, support URL, primary color, logo,
  copyright, default unit, and timezone, so the hub is white-labelable without touching
  code. `config.json` is no longer tracked in git.
- **Unified device token** — one token, auto-generated on first run and saved to
  `config.local.json` (or supplied via `SERVER_TOKEN`). It guards all mutating endpoints
  and is pushed to probes by the auto-provisioner, so plug-and-play still works while the
  API stays authenticated.
- **SQLite data layer** (`core/db.py`, WAL mode) as the system of record — see *Changed*
  for the migration — with one-time automatic import of a legacy `temperature_log.csv`,
  index-backed time-window queries, and CSV export honouring the selected range
  (`/download/temperature_log.csv?window=24h`).
- **Firmware (TempSensor)** — ESP32 firmware with stable identity, SoftAP +
  captive-portal Wi-Fi setup, mDNS advertisement, and `/provision`, `/whoami`, and
  `/status` HTTP endpoints. DS18B20 fault codes (85.0 power-on, -127/NaN disconnect) are
  rejected instead of logged as real readings.
- **Probe online/offline status** (`age_sec`, `online`) on `/api/probes` and
  `/api/health`.
- **Documentation** — customer-facing README/SUPPORT/PRIVACY plus maker docs: protocol
  spec, QC checklist, and label template.
- **Tests** — pytest suite (`tests/`) covering the API, ingest validation, and config,
  and GitHub Actions CI.

### Changed
- **Storage migrated from CSV to SQLite** (`core/db.py`). The CSV file was rewritten in
  full to add columns and read in full by the dashboard every few seconds, which caused
  blank-dashboard / corruption issues under concurrent access and did not scale. SQLite
  (WAL mode) gives safe concurrent reads while probes write, and time-window queries are
  now index-backed.
- The dashboard now queries **only the selected time window** instead of re-reading and
  re-sorting the entire history on every 5 s refresh. Large windows are downsampled for
  plotting while statistics stay exact.
- **Production server** — the app is now served by **waitress** (a production WSGI
  server) when available, on port **8088**, falling back to the Flask dev server
  otherwise.
- **Ingest hardening** — `POST /api/ingest` validates that temperatures are finite and
  within -60..150 °C and that `probe_id` matches `^[A-Za-z0-9_-]{1,32}$`;
  `GET /api/ingest` returns 405. CSV export uses a fixed
  `timestamp,temperature_c,temperature_f,probe_id` schema.
- Renamed `auto_provision.py` → `provisioning.py` and `auto_provisioner.py` →
  `provisioner.py` for clarity.
- "Connected Probes" now counts only probes seen within the online window; long-gone
  probes are pruned from the Devices list.

### Fixed
- `GET /api/config` no longer leaks `provision_token` (secret values are redacted), and
  API token comparison is now constant-time.
- Settings → Probe Setup Helper callbacks are now registered (previously dead), and the
  Wi-Fi SSID scan only runs when the Settings page is open (previously it ran every few
  seconds from app start).
- Timezone conversion handles ISO timestamps with fractional seconds + offset
  (previously the offset could be silently dropped without converting).
- `provision_device.sh` now defaults to the correct hub port (8088, was 8080).
- Removed dead modules (`core/logger.py`, `components/probe_panel.py`,
  `components/temp_graph.py`) and the broken navbar logo reference; footer/version no
  longer shows placeholder branding.

### Security
- All mutating endpoints require the device token.
- Config is redacted (secrets stripped) when returned from `GET /api/config`.
- No account, no cloud, no telemetry — readings never leave the customer's PC.

[2.4.0]: https://github.com/tallen5431/Temperature_Sensor_V2/releases/tag/v2.4.0
[2.3.0]: https://github.com/tallen5431/Temperature_Sensor_V2/releases/tag/v2.3.0
[2.2.1]: https://github.com/tallen5431/Temperature_Sensor_V2/releases/tag/v2.2.1
[2.2.0]: https://github.com/tallen5431/Temperature_Sensor_V2/releases/tag/v2.2.0
[2.1.0]: https://github.com/tallen5431/Temperature_Sensor_V2/releases/tag/v2.1.0
[2.0.0]: https://github.com/tallen5431/Temperature_Sensor_V2/releases/tag/v2.0.0
