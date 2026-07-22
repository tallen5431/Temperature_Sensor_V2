# Changelog

All notable changes to Setpoint (the PC-side hub application) and its Setpoint
ESP32 firmware are documented in this file. (Earlier entries below predate the
rebrand and refer to the product by its former name, "TempSensor".)

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
