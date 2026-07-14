# Setpoint — Materials, Readiness & What to Consider Next

This is the companion to [docs/ACTION_PLAN.md](ACTION_PLAN.md). The plan says **what to do** and in what order; this page says **what to buy**, **what must be true before money moves or a box ships**, and **what you might be missing**. It does not restate the strategy — for the revenue sequencing, margin math, and FCC gating, go to the plan. Sized for the first batch of **~13 units (10 DIY kits + 3 restaurant loaners)** plus spares, grounded in [BOM.md](BOM.md), [DIY_KIT.md](DIY_KIT.md), [QC_CHECKLIST.md](QC_CHECKLIST.md), [LABEL_TEMPLATE.md](LABEL_TEMPLATE.md), [PILOT_OFFER.md](PILOT_OFFER.md), [REV2_SCHEMATIC.md](REV2_SCHEMATIC.md), [WARRANTY.md](WARRANTY.md), and [STARTUP_CHECKLIST.md](STARTUP_CHECKLIST.md).

> **Heads-up before you order or trust the parts list:** [BOM.md](BOM.md) is **stale** — item 1 still says *ESP32-WROOM-32E DevKitC*, firmware target *WROOM-32*, LED on GPIO2, pull-up on GPIO5. The actual rev-1 board is the **ESP32-C3 SuperMini** (Amazon `B0DFWG87JS`, per [STARTUP_CHECKLIST.md](STARTUP_CHECKLIST.md)): USB-C native, **4.7 kΩ pull-up on IO5**, **LED active-low on IO8**, IO2 left unconnected. A WROOM-32E is itself a pre-certified FCC module, so trusting the stale BOM would both buy the wrong chip **and** contradict the whole "rev-1 is a bare chip, can't sell assembled" premise your strategy rests on. **Fix BOM.md before you place the parts order** (see Do-next #1).

---

## Do-next, in order

The plan's [top-5 do-now list](ACTION_PLAN.md#this-weeks-top-5-do-now-list) still holds — form the LLC, put up the Stripe link, text the restaurant, order parts + set up the flashing PC + edit the warranty, start rev-2 KiCad. This is the tighter critical-path ordering for *this* doc's concerns (buying, gates, and repo fixes), interleaved so nothing blocks the day boards land:

1. **Fix [BOM.md](BOM.md) to the ESP32-C3 SuperMini** (correct chip/price, IO5 pull-up, IO8 active-low LED, C3 firmware target) — do this **before** ordering, so the parts order is right and the docs stop contradicting the FCC premise.
2. **Place the slow overseas order today** — DS18B20 probes + TP4056 boards are the 2–4 wk long-lead items. Add a small fast Amazon backup 5-pk of each so a slow shipment never blocks your first build.
3. **Compile the firmware now — no board needed.** Run the full `arduino-cli` install + `arduino-cli compile --fqbn esp32:esp32:esp32c3` on `esp32_temp_probe/`. The FQBN/partition in `factory_flash.py` are documented-not-verified; a clean compile de-risks ~80% of the launch-day "toolchain gate" while boards are still in transit.
4. **Register one domain + stand up `support@`/`hello@`** (~$12) and find-replace every `example.com/support` in the legal docs — *before* printing a single label or card (see Readiness Gate 2 and Consider #2).
5. **Run a free USPTO knockout search** on "Setpoint" (Class 9) and "Datum Labs" before printing brand stock (Consider #3).
6. Then execute the plan's top-5 in parallel (LLC/EIN/bank → Stripe deposit link → restaurant text → warranty edit → rev-2 KiCad), and buy the materials below.

---

## Materials & tools to buy now

The **boards are NOT on this list** — the rev-1 carriers + ESP32-C3 SuperMinis are inbound. Confirm the packing slip has **≥15 SuperMinis and ≥15 carriers** (10 kits + 3 loaners + 2 spares); if tight, add spare SuperMinis (`B0DFWG87JS`, ~$3.50 ea). **Check what you already own first** — a solo maker with an R&D background very likely already has an iron, multimeter, cutters, tweezers, IPA, and an always-on PC/Pi.

### 1 · Kit BOM consumables

| Item | Qty | ~Line | Note |
|---|---|---|---|
| DS18B20 waterproof probe (1 m, stainless, 3-wire) | 20 | **$56** | ⚠️ **ORDER FIRST.** #1 return is a dead probe — buy heavy spares; QC every one before bagging. Prefer a reputable distributor (see Consider #9) |
| TP4056 charge/protect board (USB-C, **protected** variant) | 15 | **$15** | ⚠️ **ORDER FIRST.** Kits only — loaners run USB-always-on, no battery |
| Resistor assortment (incl 4.7 kΩ, 330 Ω, 100 Ω, 1/4 W) | 1 box | **$12** | Covers the mandatory 4.7 kΩ IO5 pull-up, LED 330 Ω, and 100 Ω DQ series R for pilots |
| Slide switches (SPDT, 2.54 mm) | 20-pk | **$7** | Kits' on/off; loaners omit |
| 18650 holder (or JST-PH LiPo pigtail) | 15 | **$11** | Ships in the kit; **cell NOT included** (lithium shipping rules) |
| Screw terminals (3-pin, 3.5 mm) | 25-pk | **$8** | Plug-Together tier + loaners (no-iron probe hookup) |
| Female headers (2.54 mm, snap-apart) | 10 strips | **$7** | Plug-Together: pre-soldered so buyer just seats the module |
| Male pin headers (2.54 mm) | 10 strips | **$6** | Maker tier + test rig |
| JST-PH connector kit | 1 kit | **$9** | Only if you offer the LiPo variant |
| 22 AWG hookup wire (solid, 6 colors) | 1 set | **$14** | Probe leads / internal jumps |
| Heatshrink assortment | 1 pk | **$9** | Strain-relief + a premium-feel touch per bag |
| | | **≈ $154** | |

### 2 · Flashing + bench

| Item | Qty | ~Line | Note |
|---|---|---|---|
| USB-C **data** cables (not charge-only) | 5 | **$18** | SuperMini flashes over native USB-C; a charge-only cable is a classic "won't flash" time-sink — test each |
| USB-UART adapter (CP2102/CH340, 3.3/5 V) | 3 | **$24** | Not needed for C3 kits, but required for the rev-2 UART header — buy now |
| Powered USB hub (7-port, per-port power, ≥60 W) | 1 | **$35** | Flash several boards without brownout |
| 2.4 GHz test AP / travel router | 1 | **$30** | QC needs a 2.4 GHz-only SSID (GL.iNet Mango/Beryl) |
| Bench hub (Raspberry Pi 5 8 GB) | 1 | **$110** | Runs the dashboard on `:8080`. **Skip if you already have an always-on PC/Pi** |
| Breadboard + Dupont jumper set | 1 | **$12** | Test rig / probe bring-up |
| Protected 18650 cells + charger (bench only) | 2–4 + 1 | **$22** | Observe deep-sleep wake at QC; cells never ship in kits |
| | | **≈ $251** (**$141** if you already have a Pi/PC) | |

### 3 · Assembly tools — buy only the gaps

| Item | ~Cost | Note |
|---|---|---|
| Temp-controlled soldering station | $40–110 | **Likely own.** Pinecil V2 (~$40) plenty for headers |
| Solder (63/37 rosin, 0.7 mm) | $12 | Leaded flows easiest for hand headers |
| No-clean flux pen/paste | $8 | |
| Helping hands / PCB vise + magnifier | $18 | Real time-saver for batch header soldering |
| ESD wrist strap + mat | $18 | C3 is ESD-sensitive — cheap insurance against mystery dead boards |
| Flush cutters | $10 | **Likely own** (Hakko CHP-170) |
| Multimeter (continuity + DC V) | $25 | **Likely own** — verify 3V3 rail + pull-up continuity |
| ESD fine-tip tweezers | $8 | **May own** |
| Headband magnifier / USB microscope | $25 | Solder-joint inspection at QC |
| IPA + brush + wick + sucker | $14 | **May own** — flux cleanup + rework |
| | **$178 buy-all / ~$85 incremental** | |

### 4 · Packaging + shipping

| Item | Qty | ~Line | Note |
|---|---|---|---|
| Anti-static bags (3×5 / 4×6) | 100-pk | **$11** | Board + SuperMini; premium touch |
| Small parts zip baggies (assorted) | 200+ | **$10** | Labeled baggies = perceived value at $39 |
| Kit boxes / bubble mailers (~4×6×2) | 25–50 | **$22** | |
| Thermal shipping label printer (4×6) | 1 | **$130** | One-time; serves every future batch (Rollo/Munbyn) |
| 4×6 thermal labels | 500–1000 | **$18** | Direct-thermal, no ink |
| Unit label stock (50×25 mm) | 1 roll/pk | **$15** | The `Setpoint-XXXXXX` + QR label; laser Avery sheets work if you skip a 2nd printer |
| Kraft paper / void fill | 1 roll | **$15** | |
| Digital shipping scale (~50 lb) | 1 | **$20** | Accurate postage |
| Brand/"Fragile" stickers (Setpoint by Datum Labs) | 1 run | **$30** | Doubles as the kit sticker nice-touch |
| | | **≈ $271** | |

### 5 · Restaurant pilot loaner gear

Loaners are the **hardened walk-in build**: mains USB power (no battery), DQ line protection, sealed box mounted *outside* the cold zone with only the stainless tip inside.

| Item | Qty | ~Line | Note |
|---|---|---|---|
| Sealed IP-rated box + PG7 cable gland | 5 | **$35** | Strain-relief the probe lead at the gland — the #1 field failure |
| 5 V USB mains adapter + USB-C cable | 5 | **$35** | Loaners run USB-always-on (battery dropped) |
| TVS/ESD diode for DQ (SMAJ5.0A or PESD) | 20-pk | **$8** | DQ→GND at the connector; 100 Ω series R comes from the cat-1 assortment |
| Mounting kit (neodymium magnets + 3M VHB + zip ties) | assorted | **$20** | Box mounts outside, probe routed through the door seal |
| **Mini-PC hub** ($150–250 class, N100) | 2 | **$360** | **Resale inventory, not sunk** — sell at $129–149 install fee (your cost $80–120). Buy 2 for 2–3 pilots |
| Food-safe glycol / buffer + vials | 1 | **$14** | Damp the tip so a 6-min defrost spike doesn't false-alarm |
| Small UPS (hub + router backup) — *optional* | 1 | **$55** | Offered in PILOT_OFFER; optional |
| | | **≈ $527** (**$472** w/o UPS; **$360 recoverable**) | |

### 6 · Photography — the #1 Tindie blocker

DIY_KIT: *"Photos win Tindie."* Cheapest lever with the biggest conversion impact (see Consider #13).

| Item | ~Cost | Note |
|---|---|---|
| Foldable LED lightbox/softbox (~16") | $45 | Flat-lay, hero unit, probe-in-fridge |
| Plain white + grey backdrop | $15 | Clean, honest product shots |
| Phone tripod + BT remote | $18 | Sharp, repeatable framing |
| | **≈ $78** | |

### Rough total to be "build-ready" (10 kits + 3 loaners)

| Category | Buy-all | Realistic (own core tools/PC) |
|---|---|---|
| 1 · Kit consumables | $154 | $154 |
| 2 · Flashing + bench | $251 | $141 *(use your PC, skip Pi)* |
| 3 · Assembly tools | $178 | $85 *(own iron/meter/cutters)* |
| 4 · Packaging + shipping | $271 | $271 |
| 5 · Pilot loaner gear | $527 | $472 *(skip UPS)* |
| 6 · Photography | $78 | $78 |
| **TOTAL** | **≈ $1,459** | **≈ $1,201** |

**How to read the number:** ~$360 is **resale inventory** (2 mini-PCs), recovered on the first paid install. ~$450–500 is **one-time equipment** (label printer, test router, lightbox, iron) that serves every future batch. True per-batch consumable cost is only **~$150–200** — batch two onward is cheap. Net "sunk" to be build-ready is **~$850–1,100**, comfortably inside week-one pre-order/pilot-deposit revenue.

---

## Readiness gates — before you take money / before you ship

> **Not legal, tax, or financial advice** (full one-liner at the bottom). Ordered as a gate ladder — do not skip a gate to move faster; each is cheap and load-bearing. Kits and loaner pilots need **no FCC gate** (see the plan's [legal/FCC gate table](ACTION_PLAN.md#legal--fcc-gate-table)); this is everything *else* that gates money and shipping.

| Gate | Must be true before you… | Blocking items |
|---|---|---|
| **0 — Legal shell** | …collect money into the business | LLC filed · EIN · business bank · processor paying out to that bank |
| **1 — Honest checkout** | …publish a pre-order / deposit link | FTC ship window + refund terms on the page · Returns/Warranty linked · home-state sales tax decided |
| **2 — Box readiness** | …ship a paid kit | Warranty (cap intact) + Returns in every box · serial log started · QC gate validated · handling time posted · packing slip + replacement path ready |
| **3 — Kitchen readiness** | …put hardware in a commercial kitchen | **Product-liability insurance BOUND** · W-9 + COI ready · loaner-not-sale framing · written liability limits handed over |

### Gate 0 — Legal shell (no money into the business before this)

- [ ] Form the **Datum Labs LLC** (home state, $50–500) — liability shield *and* future FCC responsible party.
- [ ] Get the **EIN free at IRS.gov** — never pay a third party. Needed before the bank account and processor.
- [ ] Open a **business bank account**; run every dollar through it (mixing funds pierces the shield).
- [ ] Create the **Stripe/Gumroad account** under the LLC + EIN, payouts pointed at the business bank. (You can *collect* into a Stripe balance sooner, but can't withdraw without the bank account.)

### Gate 1 — Honest checkout (pre-order / deposit)

**Lead with a refundable deposit, not full pre-pay** — boards are inbound and the toolchain is documented-not-verified, so a deposit de-risks both sides and keeps you FTC-clean if the build slips. It also lowers **processor-freeze risk** (see Consider #6).

| Model | Price | Use | FTC exposure |
|---|---|---|---|
| **Refundable deposit** ⭐ | $10–25 | Founding batch, before QC is validated | Lower; refund any time before ship |
| Full pre-pay | $39 | Only for buyers happy to wait the honest window | Full FTC 30-day obligation attaches |

- [ ] **Stripe Payment Link:** honest name (`Setpoint Maker Kit — Founding Batch (pre-order, ships ~4 weeks)`), deposit $10–25, **cap payments at 25**, collect email + shipping address, custom field "how many probes (1/2/4)", quantity capped so one buyer can't clear the batch.
- [ ] **Description + thank-you page restate:** the ~4-week window, "deposit fully refundable until your kit ships; if we can't ship in the window we'll notify you and you can cancel for a full refund," and what it is/isn't (kit you assemble · cell not included · ±0.5 °C typical, uncalibrated · 2.4 GHz Wi-Fi only · needs an always-on PC · loss-prevention aid, **NOT** a certified/NIST/HACCP instrument · monitoring stops in a power outage).
- [ ] **FTC Mail-Order Rule:** state an honest window (or the law defaults to 30 days); if you'll miss it, **notify + offer cancel for full refund**; refund promptly to the original method. *(Verify the exact refund wording with a small-business attorney before publishing.)*
- [ ] **Who you are:** Datum Labs LLC + a working support email; link the **real** Returns and Warranty (not `example.com/support`).
- [ ] **Sales tax:** enable Stripe Tax for your home state or track manually. **Tindie remits for you; direct Stripe/Gumroad/in-person sales are yours** — you likely owe only your home state to start.
- [ ] **Landing/waitlist page** separate from the Tindie listing: "Reserve a kit" → deposit link, plus a plain email-capture for the not-ready. **Log every reservation** (email + probe count + deposit y/n) into a CSV.

### Gate 2 — Box readiness (before any paid kit ships)

- [ ] **Edit [WARRANTY.md](WARRANTY.md) and [RETURNS.md](RETURNS.md):** insert **Datum Labs LLC + address**, swap `https://example.com/support` for the real URL, confirm the **liability cap is intact** (total liability limited to hardware price, excludes consequential/spoiled-inventory damages, "monitoring aid, not a certified/HACCP/life-safety device"), and confirm the 30-day return window + who-pays-return-shipping. Ship both in **every kit and every pilot**.
- [ ] **Start the batch serial-log CSV** with the exact [LABEL_TEMPLATE.md](LABEL_TEMPLATE.md) header: `serial,build_date,operator,mac,probe_id,ap_ssid,fw_version,test_wifi_ssid,temperature_c,ingest_ok,qc_result,notes`. One row per unit; `probe_id` unique in the file (a collision = duplicate ROM → quarantine both). **Keep it in a synced/versioned folder** (see Consider #5).
- [ ] **Validate the QC gate:** flash + full [QC_CHECKLIST.md](QC_CHECKLIST.md) on **one** board end-to-end, and flash a **second** from the browser page, **before** unlocking batch mode. Then every unit runs the gate; **any FAIL stops the unit** (note the failing step, fix, re-run).
- [ ] **Test every DS18B20 before bagging** — flash with that kit's probe connected; a dead probe reads **−127 / 85.0 / NaN**. Bag the tested probe **with its board** as a matched set.
- [ ] **Post an honest 3–5 business day handling time** on Tindie and direct checkout.
- [ ] **Packing slip per box:** order # · buyer · probe_id(s) in the box · what's included · "cell not included — use any protected 18650" · real support URL · quick-start card (`docs/kit-quickstart-card.html`) + the edited Warranty & Returns.
- [ ] **Replacement path:** DOA/defective within 30 days → you cover return shipping (prepaid label) + refund/replace, **return authorization first**; after 30 days → the 1-year limited warranty; require proof of purchase + probe_id (maps to the serial-log row).

### Gate 3 — Kitchen readiness (before hardware enters a commercial kitchen)

- [ ] **BIND product-liability insurance** (CGL **$1M/occ, $2M agg, with products-completed-operations**, ~$400–1,200/yr) — a free loaner still puts your device in a food business. Pull 2–3 broker quotes now so you have the number + a COI template.
- [ ] **W-9 ready** (LLC name + EIN) — procurement asks before B2B payment.
- [ ] **Frame the pilot as a loaner/evaluation, not a sale** ([PILOT_OFFER.md](PILOT_OFFER.md) — fill the `[BRACKETED]` fields); hand over the written liability limits.

---

## Things to consider (gaps & risks)

The strategy docs are strong on FCC sequencing, margin, and the loaner motion. These are the things that will actually bite — cheap papercuts that compound, plus a few genuine repo contradictions that would cause a wrong parts order or an indefensible claim. Ranked by "bites soonest."

**Tier 1 — bites this week / before the first box**

1. **BOM.md describes the wrong board and contradicts the FCC premise.** It lists a WROOM-32E DevKitC (a *pre-certified* module) with GPIO2 LED / GPIO5 pull-up; everything else assumes the bare C3 SuperMini (IO5 pull-up, IO8 active-low LED). → **First action:** rewrite BOM.md to the C3 SuperMini today, before ordering (Do-next #1).
2. **Every shipped legal doc still points at `example.com/support`, and there's no domain or business email.** WARRANTY, RETURNS, SUPPORT, PRIVACY all carry the placeholder; the public face is a personal Gmail. → **First action:** register a domain + `support@`/`hello@` forwarding (~$12), then one find-replace across the repo, before printing any label.
3. **No trademark clearance on "Setpoint"** — a dictionary word almost certainly crowded in USPTO Class 9 (measuring/monitoring instruments). → **First action:** run a free USPTO knockout search on "Setpoint" (Class 9) + "Datum Labs" this week; if crowded, rename before printing brand stock.
4. **The launch is gated on a toolchain never even compiled — and compiling needs no board.** The FQBN/partition are documented-not-verified. → **First action:** run `arduino-cli compile --fqbn esp32:esp32:esp32c3` on `esp32_temp_probe/` today; only the upload step then needs hardware.
5. **The batch serial-log CSV — your entire traceability/warranty spine — is a single unbacked file.** → **First action:** keep it in a git/cloud-synced folder and save after every build session.
6. **A new processor can freeze funds on pre-orders for undelivered hardware.** "$490 frozen 90–180 days" right when you need it for parts. → **First action:** default to small refundable deposits ($10–25) and email Stripe a one-line heads-up describing the pre-order model.

**Tier 2 — bites during the first pilots / first month**

7. **PILOT_OFFER discloses the power-outage caveat but not the internet-outage one** — text/email/Slack alerts die on a WAN drop, and the Tindie listing is honest about this while the pilot doc isn't. → **First action:** add one line to PILOT_OFFER's what-it-is/isn't ("alerts need the building's internet; the on-screen alarm still shows; keep the alert phone on cellular").
8. **"±0.5 °C, verified" has no per-unit verification SOP** — QC only checks "plausible room temp." Claiming "verified" without evidence manufactures the liability the docs warn against. → **First action:** add an ice-bath (slush) dip to QC, record `ice_c` in the CSV, PASS within ±0.5 °C — only then may you print "verified at 0 °C to within 0.5 °C."
9. **Counterfeit/clone DS18B20s threaten both the accuracy claim and the identity scheme** (fakes are out-of-spec and sometimes share/fake ROM codes, which your `probe_id` derives from). → **First action:** source the first/"verified" batch from Adafruit/DigiKey/Mouser, not the cheapest marketplace listing; the ice-bath step becomes your incoming clone screen.
10. **Loaner-hub reliability on a restaurant's PC has no runbook** — staff reboot, Windows auto-updates, someone closes the console; "unlimited local history" evaporates on the first reboot. → **First action:** make hub auto-start-on-boot part of the install SOP (service / Docker `restart: unless-stopped`) + a weekly CSV/SQLite export you grab on the screenshot touch.
11. **Three inconsistent power stories** — WROOM battery (BOM), C3 deep-sleep battery (plan), USB-always-on (Tindie listing) — and a deep-sleeping probe is unreachable, yet SUPPORT/QC assume its local URLs answer. → **First action:** pick one shipping power model, reconcile BOM/DIY_KIT/TINDIE_LISTING, and add "the probe answers local URLs only briefly when awake — tap reset to wake it" to SUPPORT and QC.

**Tier 3 — erodes focus, margin, and credibility over weeks**

12. **No time budget for a solo founder**, and the separate solar side-project is an unmodeled focus risk — the "this week" list is really a quarter. → **First action:** commit this week to only the revenue-critical chain (parts ordered → toolchain compiled → first pilot booked); park rev-2 KiCad and the solar project on a "not until first dollar" list.
13. **Photography is the #1 Tindie blocker with no plan** — bad phone-on-a-desk photos are why good listings underperform. → **First action:** buy a $15–25 pop-up lightbox (cat 6) and shoot on a phone in daylight. (Also delete "password" from the listing's "what's in the box" — the setup AP is open/passwordless per LABEL_TEMPLATE.)
14. **No reorder point or true per-kit COGS discipline** — the overseas lead time stalls fulfillment on a stockout, and packaging nice-touches quietly turn $23 gross into ~$12. → **First action:** set a reorder trigger (reorder probes/TP4056 at ~5 kits of stock) and add a per-kit costs line capturing packaging + label + card + a returns allowance.
15. **Security posture undercuts the on-prem/air-gapped buyer COMPLIANCE.md courts** — open setup SoftAP + unauthenticated LAN `POST /provision`, fine for a homelabber, a real objection for security-conscious B2B. → **First action:** note it honestly in the B2B pitch as a known LAN-trust assumption and put "per-unit provision secret / setup-AP password" on the near-term firmware roadmap.
16. **Competitor response and review-seeding are under-planned** — the first 3–5 Tindie reviews set the listing's trajectory, and incumbents can add a "no-cloud mode" faster than you respin. → **First action:** line up your first 3–5 warm buyers as an explicit review ask (a card in the box), and lead on the can't-be-bricked/on-prem moat, not on a price you can't win against Govee.

> **Cross-cutting:** #1, #7, and #11 are the same disease — doc-drift across partly-inconsistent product definitions. Designate **one** source-of-truth doc (BOM.md, once corrected to the C3) and reconcile DIY_KIT, TINDIE_LISTING, SUPPORT, and PILOT_OFFER to it in one pass, before anything is printed or shipped.

---

## Not legal/tax/insurance advice

This is a practitioner's checklist, not legal, tax, financial, or insurance advice — confirm the FTC refund wording, insurance timing, trademark, and sales-tax specifics with a small-business attorney, an accountant, and an insurance broker before you go live.
