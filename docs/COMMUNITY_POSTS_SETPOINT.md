# Community posts — Setpoint (homelab / self-hosted / Home Assistant)

Paste-ready copy for the **primary** channel in [`GO_TO_MARKET.md`](GO_TO_MARKET.md) §4:
community seeding. Companion to [`COMMUNITY_POSTS.md`](COMMUNITY_POSTS.md), which covers the
replacement-parts business — this file is Setpoint only.

**Why now:** you have flashed, working hardware on the bench. "I built this and it works, here's
what it took" is the strongest build-in-public post you get, and it only lands once. A pre-launch
teaser is much weaker.

---

## The positioning rules these posts follow (from `GO_TO_MARKET.md` §2)

Break these and the post reads like an ad and gets removed:

1. **Lead with local / can't-be-bricked — never with "no subscription."** Every competitor
   (SensorPush, Temp Stick) already headlines "no monthly fee." It's table stakes, so it goes in
   as a *supporting* line at most.
2. **Open firmware is not a selling point to this audience** — they can already flash an ESP32.
   Win on **packaging**: auto-discovery, a bundled dashboard, no YAML.
3. **Be honest about the boundary.** It survives an *internet/vendor* outage, not a *power*
   outage. Say so, and mention a UPS. Never overclaim.
4. **State the real requirement up front:** it needs an always-on PC/NAS on the same LAN. Saying
   this early filters out the wrong buyer instead of earning a refund later.
5. **Accuracy honestly:** ±0.5 °C typical from −10 to +85 °C, uncalibrated (DS18B20 datasheet);
   **±2 °C below −10 °C, which includes a freezer.** 0.0625 °C is *resolution*, not accuracy.
   2.4 GHz Wi-Fi only. Post the band, not just the good half — this crowd checks datasheets.
6. **Disclose that you made it,** in the first line, every time.

---

## 1. Reply template — for "what temp sensor should I use?" threads  ⭐ best channel

Highest-converting and lowest-risk: you're answering a question that was actually asked. Works in
r/homelab, r/selfhosted, r/homeassistant, r/HomeServer, r/DataHoarder (rack-heat threads).

```
If you want it fully local, the options are basically: flash an ESP32 + DS18B20 yourself
with ESPHome, buy a Shelly/Zigbee sensor and pair it to Home Assistant, or buy a cloud
thermometer and accept the account.

Worth knowing on the cloud ones: Insteon shut its servers off in 2022 and bricked
hubs overnight, and Govee's app (temp/humidity included) went dark in an AWS outage.
If that bothers you, keep it on your LAN.

Fair disclosure — I build one of these (Setpoint). It's an ESP32-C3 + DS18B20 probe that
reports to a small hub app you run on your own PC/NAS; SQLite on your disk, Prometheus
/metrics, MQTT + HA auto-discovery, CSV export, no account. The firmware is open source
(MIT) and the hub app is a free download, so you can point your own ESP32 at it without
buying anything from me:
github.com/tallen5431/Temperature_Sensor_V2

Two honest catches: it needs an always-on machine on the same network, and LAN sensors
still die in a power outage — put the router and hub on a UPS if the readings matter.
```

**Why the free-software line stays in:** it's your Rung 0 top-of-funnel ([`LAUNCH.md`](LAUNCH.md)).
The DIY-capable reader who was never going to buy hardware still becomes a user, a GitHub star, and
the person who recommends you in the next thread.

---

## 2. Build-in-public post — r/homelab / r/selfhosted

Check each sub's self-promo rules first (many require a flair, a designated day, or a
helpful-comment ratio). Post the photos: the unit, the dashboard, the rack install.

**Title:** `I got tired of cloud thermometers, so I built a local-first rack temperature monitor (open firmware + free self-hosted hub)`

```
I build embedded hardware, and I wanted rack/closet temperature monitoring that couldn't
be taken away from me. Every consumer option wanted an account and someone else's server.
Insteon bricked customers' hubs when it killed its cloud in 2022; Govee's app went down
with AWS. So I built the thing I wanted and I've been running it on my own bench.

How it works: an ESP32-C3 probe with a waterproof DS18B20 POSTs readings to a hub app you
run yourself (Windows/Linux/Docker/NAS). Readings land in a local SQLite file on your disk.
No account, no cloud, nothing phoning home.

What makes it different from rolling your own ESP32:
- Probes self-discover on the LAN over mDNS and the hub auto-provisions them — no YAML,
  no per-device config, no editing a config file to add a sensor.
- The dashboard ships with it (live chart, per-probe min/max/avg, CSV export).
- Prometheus /metrics endpoint, and MQTT + Home Assistant auto-discovery if you want it
  in an existing stack.
- Per-probe high/low thresholds with email/webhook alerts, evaluated on the hub — so they
  fire with no browser tab open.

Honest limitations, because this sub will find them anyway:
- It needs an always-on PC/NAS on the same network. If you don't have one, this is the
  wrong tool.
- 2.4 GHz Wi-Fi only.
- ±0.5 °C typical from −10 to +85 °C, uncalibrated (DS18B20 datasheet); ±2 °C below −10 °C,
  so a −18 °C freezer is in the ±2 band. The 0.0625 °C figure you'll see is resolution, not
  accuracy. There's a per-probe offset in the UI to trim against a reference.
- It survives an internet or vendor outage, NOT a power outage — the sensor and your
  router die with the power. UPS the router and hub if it matters.

The firmware is open source (MIT) and the hub app is free to download and run — if you
already have an ESP32 and a DS18B20, you can run the whole thing without buying anything
from me:
github.com/tallen5431/Temperature_Sensor_V2

I also sell it as a DIY kit for people who'd rather not source parts. Not linking it here
per the sub's rules — it's on my site if you want it. Happy to answer anything about the
firmware, the provisioning flow, or the hardware choices.
```

> **Link discipline:** lead with the GitHub repo (a gift), not the store. If the sub bans
> commercial links entirely, drop the last paragraph — the repo link still earns the traffic and
> the site is one click from the README.

---

## 3. r/homeassistant variant (lead with the HA integration)

Different audience: they don't care about your dashboard, they care that it lands in HA cleanly.

**Title:** `Local temperature probe that shows up in HA via MQTT discovery — no cloud, no YAML`

```
I built a local-first temperature probe (disclosure: it's my product) and the thing I most
wanted to get right for HA was zero-config: flip on MQTT in the hub and each probe appears
automatically as a temperature sensor through HA auto-discovery. No YAML, no manual entity
setup.

Setup is an ESP32-C3 + waterproof DS18B20 that POSTs to a small hub app on your own machine
(Docker works, runs fine on a NAS). The hub keeps its own local SQLite history and CSV
export, so you get long-term data independent of your recorder retention, and it publishes
to MQTT for HA. There's also a Prometheus /metrics endpoint if you're scraping to Grafana.

Firmware is open source (MIT), hub app is free — an existing ESP32 + DS18B20 works,
nothing to buy:
github.com/tallen5431/Temperature_Sensor_V2

Caveats: 2.4 GHz only, ±0.5 °C typical uncalibrated from −10 to +85 °C and ±2 °C outside that
band, so a freezer is in the ±2 range (there's a per-probe offset to trim it),
and it needs the hub running on something always-on. A power cut takes down the sensor and
router like any LAN device, so UPS anything you actually rely on.
```

---

## 4. Home Assistant / ESPHome community forum — project post

Forums index in Google for years, so this one is durable SEO, not just a traffic spike. Longer and
more technical is fine here.

**Title:** `Setpoint — local-first Wi-Fi temperature monitoring (open firmware + self-hosted hub, MQTT/HA discovery)`

```
Sharing a project I've been building and now running on real hardware.

Setpoint is a Wi-Fi temperature probe (ESP32-C3 + waterproof DS18B20) plus a hub app you
host yourself. The design goal was that nothing about it can be switched off by a vendor:
readings go to a local SQLite database on your machine, there's no account, and no
outbound telemetry.

Details this crowd tends to ask about:
- Discovery/provisioning: the probe advertises over mDNS (_temps-probe._tcp) and the hub
  auto-provisions it with the ingest URL + token, so adding a probe is "power it on."
  First-time Wi-Fi setup is a captive portal on the probe's own open SoftAP.
- Ingest: plain HTTP POST of JSON to /api/ingest, plus a bulk CSV endpoint the probe uses
  to drain readings buffered to flash while it was offline.
- Integrations: Prometheus /metrics, MQTT with HA auto-discovery, CSV/XLSX export.
- Alerts: per-probe high/low thresholds with hysteresis, plus offline detection with flap
  damping, evaluated hub-side. Email or webhook.
- Battery: the same firmware deep-sleeps between readings for a portable build, or runs
  always-on over USB.
- Deployment: Windows/Linux natively, or docker compose on a NAS.

Honest specs: 2.4 GHz Wi-Fi only; ±0.5 °C typical from −10 to +85 °C and ±2 °C below that
(a −18 °C freezer is in the ±2 band), uncalibrated (DS18B20 datasheet —
0.0625 °C is resolution, not accuracy, and there's a per-probe offset to trim against your
own reference). Needs an always-on machine on the same LAN. Survives internet/vendor
outages, not power outages — UPS the router and hub for anything critical.

The firmware is open source (MIT); the hub app and the browser flasher are free to use.
So you can run it on an ESP32 you already own: github.com/tallen5431/Temperature_Sensor_V2

Feedback welcome, especially on the provisioning flow and what you'd want from the alerting.
```

---

## 5. Where to post (ranked by fit)

| Community | Fit | Notes |
|---|---|---|
| **r/homelab** | ⭐ Primary | The sharpest fit — they already run an always-on box. Read the self-promo rules; lead with the repo. |
| **r/selfhosted** | ⭐ Primary | "No cloud" *is* the value proposition here. Strongest reception for the free hub. |
| **r/homeassistant** | ⭐ Primary | Use the MQTT-discovery variant (#3), not the generic post. |
| **HA / ESPHome community forums** | Primary (durable) | Slower burn, but indexes in search for years. Use #4. |
| **r/HomeServer, r/DataHoarder, r/sysadmin** | Secondary | Reply-only (#1) on rack-heat / server-closet threads. Don't cold-post a product. |
| **Grow / brew forums & Discords** | Later | Only once you push the SHT4x VPD variant — the wedge there is Pulse's VPD paywall (`GO_TO_MARKET.md` §1 #2). |
| **Niche YouTube / blog reviewers** | Secondary | Seed 2–3 review units. Slow, compounding, closes the solo-maker trust gap. |

## 6. Prep the repo first — it is the link every post points at

Every post above sends people to GitHub, so fix the landing experience *before* posting. The repo
is public, but as of this writing it has **0 stars and 0 forks**, and GitHub is itself a discovery
channel you're currently not using. All of this is free:

- [ ] **Add repo topics.** This is how people browse GitHub: `homelab`, `selfhosted`,
      `home-assistant`, `esp32`, `esp32-c3`, `temperature-monitoring`, `iot`, `mqtt`,
      `prometheus`, `local-first`. Settings → About → Topics.
- [ ] **Write the About description** — one line, benefit-first: *"Local-first Wi-Fi temperature
      monitoring. Your own hub, your own SQLite, no cloud or account."* It's the text that shows
      in every GitHub search result and social embed.
- [ ] **Consider renaming the repo `setpoint`.** `Temperature_Sensor_V2` reads like a dev folder
      and undersells the product in the one link you're promoting. GitHub redirects the old URL
      after a rename, so it's low-risk — but update `DOCS_URL` in `core/version.py` and the site
      links when you do.
- [ ] **Hero image + dashboard screenshot at the top of the README.** A reader decides in about
      three seconds; a wall of text loses them.
- [ ] **Pin the browser flasher link high in the README** — one-click flashing is the magic
      moment, and it's the lowest-friction thing a curious visitor can do.
- [ ] **Submit to [awesome-selfhosted](https://github.com/awesome-selfhosted/awesome-selfhosted)**
      once the README is presentable. It's a durable, high-intent traffic source for exactly this
      audience, and inclusion is free — read their submission criteria first.

## Rules of the road

- **Disclose you built it, in the first line.** Every time. This audience punishes stealth
  marketing harder than it punishes selling.
- **Read each sub's self-promotion policy before posting.** Several ban commercial links
  outright; the repo link is almost always allowed where a store link is not.
- **Don't paste the same text twice.** Tailor the opening line per community — identical
  cross-posts read as spam and get filtered.
- **Answer every comment**, especially the skeptical ones. The comment thread is what converts,
  not the post.
- **90/10:** be useful nine times for every time you mention the product.
- **Never post a spec you haven't measured.** Battery life stays "weeks" until the bench test
  gives a real number (see the honest-specs framing in `TINDIE_LISTING.md`).

## Keep in sync by hand

These appear across the go-to-market docs and the site — change them together (see
"Keep in sync by hand" in [`../site/README.md`](../site/README.md)):

- **DIY kit price** — currently **$39**.
- **Battery life** — do **not** claim "weeks." `site/field-test.html` states run-to-empty "was not exercised and remains pending," so say the hardware (USB-C, 18650, hard power switch) and leave runtime unstated until measured.
- **Firmware version** — currently **2.8.2** (hub **2.6.2**).
- **Accuracy claim** — ±0.5 °C typical from −10 to +85 °C, ±2 °C outside that band, uncalibrated. Post the whole band, never just the ±0.5 half. Only a unit that passed the ice-bath
  check in [`QC_CHECKLIST.md`](QC_CHECKLIST.md) §5.3 may be described as "verified at 0 °C to
  within ±0.5 °C."
