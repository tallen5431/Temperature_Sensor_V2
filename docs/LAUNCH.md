# Setpoint — Launch Runbook (start selling small, scale when it makes sense)

> **The core principle: stop building features and start selling.** The product is
> feature-complete for a first market (hub + firmware + docs + integrations). The
> remaining work to earn revenue is business/ops, not code. Sell → learn → scale.
>
> See `docs/GO_TO_MARKET.md` (positioning/pricing/channels) and `docs/COMPLIANCE.md`
> (the legal detail) for the "why" behind each step below.

---

## The lowest-barrier ladder — start with hobbyists, climb as revenue justifies

The single biggest barrier to selling a wireless gadget is **FCC/CE**. Hobbyists let
you sidestep most of it, because you can sell at a lower "readiness" tier. Start on the
bottom rung (near-zero cost and risk), and only climb when demand is proven. Each rung
reuses everything below it.

**Rung 0 — Software + "bring your own hardware" ($0, no compliance, do this now).**
Setpoint is already free, local-first software. Publish it plus the firmware and the
**browser-flash page** (`flash/`, powered by ESP Web Tools): a homelabber opens a link,
clicks one button, and flashes their own ESP32 + DS18B20 from Chrome — no toolchain, no
account. You ship bytes: no inventory, no FCC. This **builds the audience and validates
demand before you spend a dollar** on parts, and the flash link is your best top-of-funnel.

**Rung 1 — Kits (low barrier, low capital).** Sell a bag of parts (ESP32 + DS18B20 +
4.7 kΩ pull-up + battery/TP4056 + enclosure + a label/QR to the flash page). Kits sold to
hobbyists sit largely outside finished-product FCC equipment authorization, and the
ESP32-WROOM module is already FCC/CE-certified as a radio. Low capital — buy parts in 10s,
bag them by hand. Sell on **Tindie** — the best-fit maker marketplace (≤48 h store approval,
5% fee, no upfront cost). A ready-to-paste listing is in [`TINDIE_LISTING.md`](TINDIE_LISTING.md).

> **Tindie is exclusive:** a product listed on Tindie **can't be sold elsewhere on the web** at the
> same time. So pick Tindie as your **one paid channel for the probe**, and keep your own site for the
> **free software + waitlist + build-in-public** (Rung 0) — not a competing listing of the same SKU.

**Rung 2 — Pre-assembled, pre-flashed probes (medium barrier).** This is what
`docs/BOM.md` + `docs/QC_CHECKLIST.md` are built for. Because you're on a pre-certified
module, a finished unit needs an **FCC Part 15B SDoC** — a *self*-declaration with
self-testing, **not** a lab filing with the FCC (see Phase 1 and `docs/COMPLIANCE.md`).
Graduate here once kits prove demand.

**Rung 3 — Small business / regulated (later).** Facilities, restaurants, labs, and
greenhouses, where the **audit trail + calibration + alerts** become the selling points →
then NIST-traceable calibration + full certification for regulated cold-chain buyers.

> Not legal advice — confirm the exact FCC path with a test lab/consultant before selling
> **assembled** units. Rungs 0–1 avoid that gate; the phases below detail Rung 2 onward.

---

## Lead product for launch (decided for speed)

**Homelab / server-room probe, always-on USB, DS18B20, temperature-only.** Why this first:
- It's the **default firmware build** — no SHT4x, no battery, cheapest BOM, fastest to assemble.
- It fits the **sharpest-demand niche** (buyers already run an always-on PC on the same LAN).
- **Always-on power** keeps the plug-and-play discovery/provisioning that is the headline feature.

**On battery:** the firmware **already supports deep-sleep battery operation** in the same
sketch (it deep-sleeps between readings when the interval is ≥ ~10 s, and stays always-on
below that). So a battery probe is a *packaging* choice (cell + TP4056 charger, in the BOM),
not a future architecture change — lead with always-on USB for the homelab niche because it's
simplest, and offer the battery build when portable/remote demand shows up.

Fast-follow once the first batch sells: the **grow variant** (SHT4x → humidity/VPD, already built).

---

## Phase 0 — Validate this week ($0, no compliance needed)

Nothing here requires FCC or inventory. Do it before spending a dollar on hardware.

- [ ] **Tag a release** and publish the repo (see "Cut the release" below).
- [ ] **Publish the browser-flash page** (`flash/` on GitHub Pages — see `flash/README.md`).
      A "flash it yourself from Chrome" link is the lowest-friction Rung-0 on-ramp and a great
      thing to drop into the launch post.
- [ ] **Build in public** — a "here's what I made and why" post in r/homelab, r/selfhosted,
      r/homeassistant and the Home Assistant / ESPHome forums. Disclose you built it; lead with
      *"no cloud, runs on your own PC, can't be bricked."* Link the repo.
- [ ] **One-page landing + email waitlist.** A/B test two headlines: *"can't be bricked / no cloud"*
      vs *"no subscription."* Measure email-capture rate.
- [ ] **Crowd Supply "coming soon" page** (free) — watch the "notify me" count.
- [ ] Seed **2–3 niche YouTube/blog reviewers** with a "review unit coming" offer.

**Go/no-go signal:** real "where do I buy / take my money" replies, waitlist sign-ups, GitHub stars.
If interest is thin, iterate the pitch *before* buying parts.

---

## Phase 1 — Clear the one legal gate (parallel with Phase 0; ~2–4 weeks, ~$1–3k)

You may **not** legally sell a Wi-Fi device in the US without this. The pre-certified ESP32 module
saves the big cost, but the finished unit still needs:

- [ ] **FCC Part 15 Subpart B SDoC** — test the assembled unit as a Class B unintentional radiator,
      keep the signed test report. No FCC ID/fee, but you need a **US-located responsible party**.
      Budget ~$1–3k for a multi-port hub; 2–4 weeks.
- [ ] **Labeling** — *"Contains FCC ID: [Espressif module ID]"* + the §15.19(a)(3) statement on
      every unit (or e-label per KDB 784748).
- [ ] Confirm you stay inside Espressif's module integration conditions + RF-exposure check.
- [ ] **Product-liability insurance** (CGL ~$1M/occ, $2M agg + products) and a **W-9** — B2B
      procurement asks for both; cheap to have ready.

> Do NOT list on Amazon, run paid ads, or sell at volume before this is done. A first hand-built
> batch to a warm audience should still wait on the SDoC — sequence it early.

---

## Phase 2 — First small batch & first sales

- [ ] **Hand-build 5–10 units** per `docs/BOM.md` + `docs/ASSEMBLY.md`.
- [ ] **Flash + QC + label** each with `firmware/factory_flash.py` and `docs/QC_CHECKLIST.md`
      (unique `TempSensor-<HEX>` serial, SoftAP up, plausible reading, one successful bench POST).
- [ ] **Sell direct** to the Phase-0 waitlist on **Tindie** (maker audience, ≤48 h approval, 5% fee) —
      use the ready-to-paste [`TINDIE_LISTING.md`](TINDIE_LISTING.md). Because Tindie is web-exclusive,
      pick it *or* your own **Shopify/Gumroad** page for the paid probe, not both. Price the **1-probe
      starter at ~$69** (or a **DIY kit at ~$39** to sell before the FCC step); a 4-probe pack at ~$189.
- [ ] Require **real payment or a refundable deposit** — getting the first ~10 people to pay is the
      truest validation.
- [ ] Ship with a one-page quick-start (point to `docs/USER_MANUAL.md`) and ask every buyer for
      feedback + a review.

---

## Phase 3 — Scale only when the signal is real

**Gate:** don't scale until you have ~10+ real sales, low return/support load, and repeat/word-of-mouth demand.

- [ ] Larger batch (order boards/enclosures in quantity; per-unit cost drops).
- [ ] Ship the **grow (SHT4x) variant** for the #2 niche — VPD is already built; market
      *"VPD alerts, no subscription"* vs Pulse.
- [ ] Offer a **per-unit calibration option** (the SHT4x per-unit accredited cert is free; outsource
      DS18B20 cal ~$140 when a buyer needs it) to reach food-service/HACCP-support buyers.
- [ ] Consider **MSP/VAR** channels (recurring monitoring — strong fit for the no-cloud angle).
- [ ] Consider **EU/UK** only when revenue justifies it (COMPLIANCE.md Phase 3: RED + EN 18031 +
      RoHS/REACH + EU rep + WEEE).
- [ ] Ship the **battery build** (deep-sleep firmware is already in the sketch — just add the
      cell + TP4056 charger from the BOM) if remote/portable demand shows up.

---

## What NOT to do yet (protect focus + cash)

- ❌ **More features.** The product is ready for the lead market. Ship it.
- ❌ **Amazon / Etsy** — fee + compliance friction, wrong audience early.
- ❌ **EU** — do it after US revenue justifies the lab spend.
- ❌ **Regulated segments** (vaccine/pharma/accredited cold-chain) — effectively closed without a
      funded validated product line; never claim compliance you don't have.
- ❌ **A separate battery SKU at launch** — the deep-sleep firmware already exists, so it's a
      packaging option, not new work; still, lead with one always-on USB build to keep focus.

---

## Cut the release

**v2.4.0 is already merged to `main`** — the "first sellable build." To turn it into a
tagged release (and for every release after), on your own machine:

1. Confirm the version is consistent: `core/version.py` (`HUB_VERSION`), `pyproject.toml`,
   `firmware/src/protocol.h`, and `esp32_temp_probe/esp32_temp_probe.ino` (`FW_VERSION`) —
   currently all **2.4.0** — and that `CHANGELOG.md`'s top entry names that version.
2. `pytest` (all green), then tag and push: `git tag v2.4.0 && git push origin v2.4.0`, and
   create a **GitHub Release** from that tag. (Tag pushes are blocked in the automated cloud
   environment, so cut the tag/release locally or from the GitHub UI.)
3. Note the released commit/version on your QC labels so every shipped unit is traceable.
