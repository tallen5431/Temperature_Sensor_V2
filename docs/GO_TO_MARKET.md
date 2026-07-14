# Setpoint — Go-to-Market Strategy

> A practical plan for selling a small-batch, local-first temperature-monitoring product
> online. Grounded in market research (competitor pricing, community sizes, and documented
> failure modes as of 2025–2026). Treat willingness-to-pay figures as competitor *list-price
> ceilings*, not guaranteed margins — **validate with real deposits before building 100 units.**

---

## TL;DR

- **Lead niche:** homelab / self-hosted / small server-room & IT-closet monitoring. It's the
  sharpest fit for a "hub app on your own PC," because that buyer *already* runs an always-on
  machine on the same LAN.
- **Position on "can't be bricked / no cloud,"** *not* "no subscription" — the latter is already
  the headline of the category leaders (SensorPush, Temp Stick), so it's table-stakes.
- **Make the hub software free; sell probes in bundles.** ~$69 starter, ~$189 four-probe kit.
- **Go to market community-first** (Home Assistant/ESPHome, r/homelab, r/selfhosted) → own
  Shopify store → Crowd Supply launch. Avoid Amazon/Etsy early.
- **Validate cheaply first:** build-in-public post + landing-page waitlist + 5–10 hand-built
  units sold to the warm audience at real prices.

---

## 1. Where the demand is (ranked beachheads)

### #1 — Homelab / self-hosted / server room & IT closet  ⭐ start here
- **Why it fits best:** the customer already has an always-on PC/NAS/server on the same network,
  so "run the hub on your own machine" is *zero* added friction — unlike remote cabins/RVs where
  a self-hosted PC is a dealbreaker. Temperature-only is sufficient (heat, not humidity, is the
  concern). Multi-probe maps to racks/closets/sites.
- **Buyer:** the hobbyist who has outgrown DIY, or a time-poor SMB sysadmin/MSP protecting a rack
  where downtime is expensive.
- **Willingness to pay:** bimodal. Hobbyist floor ~$5–40 (they flash their own ESP32 — *don't*
  compete there). Prosumer/SMB ~$150–600+ (Temp Stick $149 single; AKCP/Room Alert SMB gear
  $67–140 per sensor **plus** a base unit).
- **The catch (real):** this audience is the *most* able to DIY, so "open firmware" is not a
  differentiator to them. **Win on packaging** — auto-discovery, a bundled dashboard, no YAML —
  vs. Shelly/ESPHome, and monetize DIYers with a cheap firmware/white-label tier.
- **Product moves that unlock it (shipped in this repo):** ✅ Prometheus `/metrics`, ✅ optional
  MQTT + Home Assistant auto-discovery, ✅ Docker/headless deployment, ✅ optional dashboard login
  for shared office LANs. Still on the roadmap: syslog/SNMP alert channels, site/rack grouping.

### #2 — Indoor grow tents / small greenhouse / cannabis
- **Why:** highest willingness-to-pay of any well-fit niche and the clearest *subscription-pain*
  wedge — the category monitor **Pulse** gates VPD alerts and history behind **$10–35/mo**, and
  reviewers cite that paywall as a top complaint. Growers are technical, run a home PC, need
  multiple probes, and (for cannabis) have a genuine privacy motive.
- **WTP:** $129–499 observed (Pulse Zero $129 / One $199 / Pro $499).
- **The old blocker — now cleared (shipped in this repo):** this niche buys on **VPD**, which
  needs **humidity**. Setpoint was temperature-only; that gap is now closed. A **SHT4x
  temperature + humidity** firmware variant (`-D SENSOR_SHT4x`) ships, the hub **computes VPD
  itself** (Tetens formula, with an optional leaf-temperature offset) from every reading, and
  Humidity + VPD now surface on the dashboard, in Prometheus `/metrics`, and via MQTT/Home
  Assistant discovery — with **per-probe humidity and VPD alert thresholds**. The core VPD
  wedge is met, with **no paywall** (directly vs. Pulse's gated VPD).
- **Product moves — shipped vs. remaining:** ✅ SHT4x humidity firmware variant, ✅ hub-computed
  **VPD** (+ optional leaf offset), ✅ Humidity/VPD on dashboard, `/metrics`, and MQTT, ✅ VPD +
  humidity alerts. Still on the roadmap: day/night VPD schedules and a **CO₂** sensor option
  (the main remaining grow variable). Now that RH/VPD ships, price a no-subscription VPD kit at
  ~$149–199 and hammer *"VPD alerts never behind a paywall."*

### #3 — Homebrewing / fermentation / cheese & charcuterie curing
- **Why:** strongest ethos/community fit (technical, fee-averse, want local data, multi-vessel).
  A good low-cost **credibility & reviews** beachhead — but a **volume/word-of-mouth play, not a
  margin play.** The field is crowded and cheap (Inkbird ITC-308 ~$25–51 is the default), and
  homebrew participation is declining. The curing "humidity gap" is *already* filled by Inkbird's
  IHC-200. Use it to seed community, not for profit.

### Niches to approach with caution
- **Cabins / RVs / vacation-home freeze alarms** — *highest raw consumer demand* but a poor fit:
  the property is unattended with no PC, and needs **remote/cellular** alerting. Don't lead here
  until a standalone always-on hub or relay exists. (Note: "no-fee" cabin monitors like CabinPulse
  actually carry a ~$10–14/mo cellular plan.)
- **Regulated (vaccine/VFC, restaurant HACCP, cold-chain, clinical labs)** — strongest,
  least-discretionary demand, but structurally **closed to an uncertified open device**: VFC
  mandates an ISO-17025 NIST-traceable calibration certificate with periodic recertification.
  Chasing it requires paid certification and a managed/support model — which negates the
  open/no-subscription pitch. A later, separate business.

---

## 2. Positioning

> **"Setpoint answers to you, not a server.** It runs entirely on your own PC and network — no
> cloud, no account, no subscription — so your temperature data never leaves the building, and
> your alerts keep firing on your LAN even when the internet drops or the company that sold it to
> you is gone."

Lead with **can't-be-bricked / local**, backed by real, un-escapable competitor failure modes:
the Insteon 2022 cloud shutdown that bricked customers' hubs overnight, and Govee's own admission
its app (including temp/humidity) went dark during an AWS outage. Keep **"no monthly fee"** and
**"one hub, many probes"** as *supporting* bullets.

**Be honest about the boundary:** this claims resilience to an *internet/vendor* outage, not a
*power* outage — LAN sensors and the router die when the site loses power (the #1 freezer-alarm
failure). Pair the message with a *"put your router on a UPS"* note; never overclaim.

### Messaging angles
1. **"It can't be shut down."** Open firmware on *your* PC survives any vendor's death. *(lead)*
2. **"Your data never leaves the building."** Local database (one-click CSV export), no account, no cloud retention.
3. **"Keeps alerting on your own network even when the internet is down."** *(+ the UPS caveat)*
4. **"One hub, many probes — pay for sensors, not per-sensor gateways."** Attacks SensorPush's
   $55 sensor + $100 gateway math directly.
5. **"No account. No login. No app-store gatekeeper."** Sidesteps forced app migrations (Inkbird,
   Tuya/Smart Life) that stranded other buyers' data.
6. **"Own your records: unlimited local history, one-click CSV, calibration you control."**

---

## 3. Pricing

Anchor against **competitors**, not your ~$14–17 BOM. Never lead the discount on "subscription
savings" (rivals already match no-fee).

| Item | Price | Rationale |
|---|---|---|
| Hub software | **Free** | It's just software on the customer's PC → anchor "no gateway tax, nothing to rent" against SensorPush's $100 gateway and Pulse's monthly fee. |
| 1-probe Starter | **~$69** | Undercuts Temp Stick ($149) and SensorPush ($155 for one remote sensor). |
| 2-probe | **~$109** (~$55/probe) | Visible per-probe quantity anchor. |
| 4-probe "Whole-Closet / Whole-Grow" kit | **~$189** (~$47/probe) | Beats the equivalent SensorPush/Temp Stick multi-sensor total; healthy margin on ~$14–17 BOM. |
| Maker / white-label tier | bare boards or firmware + BOM | Converts DIY cannibalization into a low-support revenue line. |
| VPD kit (RH/VPD now shipped) | **~$149–199** | *"VPD alerts never behind a paywall"* vs. Pulse. |

Frame the sale on **5-year total cost of ownership**: competitors are "subscription-free" but you
re-buy a $100 gateway per ecosystem or rent Pulse's cloud goodwill; Setpoint has nothing to rent
and *cannot be paywalled later*. Deliberately **do not chase the ~$15 Govee floor** — unwinnable
and off-strategy.

---

## 4. Channels

| Channel | Fit | Notes |
|---|---|---|
| **Community seeding** (Home Assistant/ESPHome, r/homelab, r/selfhosted, r/homeassistant, grow/brew forums & Discords) | **Primary** | Highest-fit, lowest-cost motion — exactly how Apollo Automation scaled from a basement to a factory. Build in public, open the firmware, iterate publicly. Respect the 90/10 rule and per-sub promo bans; disclose "I built this," solve the problem, mention the product last. This feeds every other channel. |
| **Owned store** (Shopify Basic ~$29–39/mo or WooCommerce) | **Primary** | Best long-term margin/data/email-list; the only channel that supports white-label, firmware downloads, and direct support. Has *no native traffic* — only works paired with the community engine. |
| **Crowd Supply** (~12% + processing) | **Primary (launch)** | Best-fit open-hardware launch platform; de-risks manufacturing by placing its own follow-on order (50–100% of what backers raise) and handling fulfillment. Requires an application. |
| **Tindie** (<~10% all-in) | Secondary | Native maker/ESP32 audience but thin organic discovery — use as a cheap on-audience checkout for buyers you refer. |
| **Niche YouTube / blog reviewers** | Secondary | Durable SEO + third-party trust; seed 2–3 review units. Slow but compounding; closes the solo-maker trust gap. |
| **Kickstarter** (~8–10%, all-or-nothing) | Secondary | Only if you need launch capital/mainstream reach over audience fit. No fulfillment help. |
| **Amazon** (8–15% + $39.99/mo + FBA) | **Avoid early** | FCC Part 15 for the WiFi radio, labeling, brand-registry hassle, price war vs cloud thermometers, thin margins. Revisit only for mainstream volume much later. |
| **Etsy** (~20–25% w/ Offsite Ads) | Avoid | Wrong audience (craft/gift shoppers). |
| **eBay** | Avoid | Deal hunters, no brand/community value. Inventory clearance only. |

---

## 5. Validate before you build 100 units

1. **Landing page + waitlist** (~$0–40). A/B test the two headlines — *"no cloud / can't be
   bricked"* vs *"no subscription"* — and measure email conversion. This also validates the
   positioning thesis.
2. **Build in public on GitHub + the HA/ESPHome forums + r/homelab.** Watch stars, comments, and
   "where do I buy" replies over 2–4 weeks.
3. **Crowd Supply "coming soon" page** — free; watch the "notify me" subscriber count.
4. **Hand-build 5–10 units and sell them** to the warm forum audience at real target prices
   ($69 / $189) — require *payment or a refundable deposit*, not a survey. Getting the first ~10
   people to pay real money is the truest pre-100-unit signal.
5. **Fake-door price test:** Shopify pre-order deposits / Tindie favorites at each price point.
6. **Ship review units** to 2–3 niche reviewers; track referral traffic and pre-orders.
7. **For the grow niche:** the RH/VPD firmware (SHT4x) now ships, so validate VPD-paywall
   frustration on grow forums to confirm the switcher pool *before* committing grow-kit
   inventory. Homelab still leads the launch.

### Demand signals to watch
- Upvotes / "take my money" replies on a build-in-public post (the cheapest early read).
- GitHub stars/forks/issues on the open firmware + hub repo.
- Crowd Supply pre-launch subscriber count; landing-page email conversion %.
- Tindie favorites and Shopify pre-order deposits (real WTP > survey "yes").
- Volume/recency of forum threads asking for a "local, no-cloud, multi-probe temperature monitor,"
  and pain threads about Pulse/SensorPush subscriptions and cloud outages (your switcher pool).

---

## 6. Top risks (and mitigations)

- **DIY cannibalization** in the #1 niche — target the *time-poor* prosumer/SMB who wants
  out-of-box packaging; monetize DIYers via a firmware/white-label tier.
- **Positioning trap** — "no subscription" is already the incumbents' headline; hold discipline
  and lead on no-cloud/can't-be-bricked.
- **Self-hosted-PC friction** blocks the highest-demand *consumer* niche (cabins/RVs) — don't
  lead there without a standalone/relay option.
- **Humidity is the binding variable** for grow/curing/mushroom — RH/VPD now ships for the grow
  variant (SHT4x + hub-computed VPD); a **CO₂** option and humidity set-point control are the
  remaining gaps before a full push into those niches.
- **Power-outage failure mode** — never overclaim "works when the internet is down"; pair with a
  UPS recommendation.
- **Solo-maker trust gap & support burden** vs polished incumbent apps — lean on reviews,
  build-in-public credibility, and a focused niche.
- **Regulated segments** (vaccine/HACCP/cold-chain/labs) are closed without certification — a
  separate, later business, not a beachhead.
- **Homebrew** is thin-margin and shrinking — community/credibility volume only.
- **Evidence quality** — WTP figures are competitor list-price ceilings; community sizes are
  largely anecdotal; no hard search-volume data was obtainable. **Validate with real deposits.**

---

## 7. Key sources

- Temp Stick ($149, "No Subscription" in the listing title) and SensorPush ($55 HT1 + $99.95 G1
  gateway, "No Monthly Fee") — proof "no monthly fee" is table-stakes; the per-sensor+gateway
  wedge to attack.
- Pulse ($199–499 hardware + $10–35/mo alert paywall) — the grow-niche subscription wedge.
- Insteon 2022 abrupt cloud shutdown; Govee AWS-outage app downtime — the "can't-be-bricked"
  proof points.
- Apollo Automation year-in-review — the community-led, build-in-public ESP32 maker playbook.
- Crowd Supply apply page — open-hardware launch platform with manufacturing de-risk.
- r/homelab & r/selfhosted community sizes; `pvvx/ATC_MiThermometer` — homelab scale *and* the
  DIY-cannibalization risk.
- Inkbird ITC-308 / IHC-200 + homebrew-decline coverage — crowded, shrinking homebrew niche.
- VFC / EZIZ digital data-logger requirements — the certification moat for regulated monitoring.
- Best-WiFi-freezer-alarm guides — the power-outage/UPS honesty caveat.
