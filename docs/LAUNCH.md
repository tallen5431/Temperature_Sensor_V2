# ThermaHub — Launch Runbook (start selling small, scale when it makes sense)

> **The core principle: stop building features and start selling.** The product is
> feature-complete for a first market (hub + firmware + docs + integrations). The
> remaining work to earn revenue is business/ops, not code. Sell → learn → scale.
>
> See `docs/GO_TO_MARKET.md` (positioning/pricing/channels) and `docs/COMPLIANCE.md`
> (the legal detail) for the "why" behind each step below.

## Lead product for launch (decided for speed)

**Homelab / server-room probe, always-on USB, DS18B20, temperature-only.** Why this first:
- It's the **default firmware build** — no SHT4x, no battery, cheapest BOM, fastest to assemble.
- It fits the **sharpest-demand niche** (buyers already run an always-on PC on the same LAN).
- **Always-on power** keeps the plug-and-play discovery/provisioning that is the headline feature.

Fast-follows once the first batch sells: the **grow variant** (SHT4x → humidity/VPD, already built)
and — only if the application needs it — a **battery/deep-sleep variant** (a real architecture
change; don't let it block launch).

---

## Phase 0 — Validate this week ($0, no compliance needed)

Nothing here requires FCC or inventory. Do it before spending a dollar on hardware.

- [ ] **Tag a release** and publish the repo (see "Cut the release" below).
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
      (unique `ThermaProbe-<HEX>` serial, SoftAP up, plausible reading, one successful bench POST).
- [ ] **Sell direct** to the Phase-0 waitlist: **Tindie** (maker audience, low fee) or a simple
      **Shopify/Gumroad** page. Price the **1-probe starter at ~$69**; offer a 4-probe kit at ~$189.
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
- [ ] Decide on a **battery/deep-sleep variant** if remote/portable demand shows up.

---

## What NOT to do yet (protect focus + cash)

- ❌ **More features.** The product is ready for the lead market. Ship it.
- ❌ **Amazon / Etsy** — fee + compliance friction, wrong audience early.
- ❌ **EU** — do it after US revenue justifies the lab spend.
- ❌ **Regulated segments** (vaccine/pharma/accredited cold-chain) — effectively closed without a
      funded validated product line; never claim compliance you don't have.
- ❌ **Battery/deep-sleep** — a v2 architecture decision, not a launch blocker.

---

## Cut the release (do first)

1. The current `[Unreleased]` work is a coherent milestone — finalize `CHANGELOG.md` under a version
   (e.g. **2.1.0**), bump `core/version.py`, `pyproject.toml`, and `firmware/src/protocol.h`.
2. `pytest` (all green), then tag: `git tag v2.1.0 && git push --tags`.
3. Open a PR to `main`; that tagged commit is your "first sellable build" — note it on QC labels.
