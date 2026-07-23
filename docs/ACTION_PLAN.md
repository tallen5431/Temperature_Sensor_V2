# Setpoint / Datum Labs — Master Action Plan

*The single index for how to make money now and scale legally later. Deeper detail lives in the linked repo docs; this page is the map.*

## North Star

**Validate demand with near-zero-cost DIY kits and free restaurant loaner pilots to generate revenue NOW — and spend real money on the rev-2 respin + FCC only once that demand is proven.** The logic is deliberately revenue-first: the two fastest cash paths (kits, loaner pilots) need **no FCC certification and near-zero capital**, so they can earn *this month* while the certified assembled product is still on the drawing board. Every dollar you eventually spend on rev-2 and the FCC SDoC is **funded by revenue you already collected**, never borrowed against a hope. Compliance work should always trail demand — it must never block the first sale.

---

## SECURE REVENUE ASAP — priority stack

Ranked by speed-to-first-dollar. **Run the top three in parallel starting this week.** Everything here is FCC-clean because you are selling *kits, service, software, deposits, or a certified PC* — **never an assembled rev-1 radio.**

### 1. Paid pre-orders / founding-batch deposits ⭐ fastest clean dollar
A Stripe Payment Link or Gumroad "pre-order" for the **Maker Kit**, sold to your build-in-public audience and warm contacts before a single kit is bagged.
- **First dollar:** 2–5 days. **Per sale:** $39 full pre-pay, or a $10–25 refundable deposit that locks a founding price. 10 pre-orders = **$200–490 in week one.**
- **First 3 actions:**
  - [ ] Create a Stripe Payment Link: *"Setpoint Maker Kit — Founding Batch (pre-order, ships ~4 wks)"*, qty cap 25.
  - [ ] Post it once (README banner + r/homelab + r/selfhosted + text your restaurant contacts) with an **honest** ship window.
  - [ ] Add a "Reserve a kit" button to your landing page; log every buyer email + probe count.
- **Gotcha:** pre-sell the **kit, not an assembled unit**. FTC mail-order rule: if you take full payment, ship within the stated window (or 30 days) or refund. Keep deposits refundable.

### 2. Restaurant loaner pilot → deposit + setup/PC fee
Your warm restaurant contacts are the highest-value edge. Run the **free 30-day loaner pilot** (FCC-clean evaluation), but structure two clean cash flows around it: a **founding-customer reservation deposit** ($100–250, locks a per-kitchen price on future certified probes) and a **paid install** — bring a $150–250 mini-PC, install the free hub, charge **$150–400 for labor + the certified PC**. The *probe stays a loaner*; you bill labor + an already-FCC'd computer, not the uncertified radio.
- **First dollar:** 1–2 weeks (one install with a warm contact). **Per sale:** $100–500 deposit + $150–400 setup; a converted 4-probe kitchen is ~$329 later.
- **First 3 actions:**
  - [ ] Fill the `[BRACKETED]` fields in [docs/PILOT_OFFER.md](PILOT_OFFER.md); text your two warmest contacts to book a 30-min install.
  - [ ] Build + QC 2–3 loaner units the day boards land; label each with serial + firmware version.
  - [ ] Draft a one-line "Founding-Customer Reservation" (deposit, locked probe price, refundable-if-we-don't-ship).
- **Gotcha:** do **not** "sell" an assembled rev-1 probe. Loaner + labor + certified PC + future-delivery deposit only. Have LLC + insurance quote + W-9 ready — procurement asks.

### 3. Tindie DIY-kit listing (Maker $39 / Plug-Together $49)
The designated first storefront. Copy is paste-ready in [docs/TINDIE_LISTING.md](TINDIE_LISTING.md); store name = **Datum Labs**.
- **First dollar:** 2–4 weeks (gated on boards arriving + one hero-unit photo + <48 h store approval). **Per sale:** $39–49, ~$23–30 gross.
- **First 3 actions:**
  - [ ] Day boards land: build + QC one hero unit ([docs/QC_CHECKLIST.md](QC_CHECKLIST.md)); confirm it reads room temp (not −127).
  - [ ] Shoot the parts flat-lay + assembled unit + dashboard-on-laptop + probe-in-context photos.
  - [ ] Paste the listing, set $39/$49 + real shipping + inventory, swap the support link, publish **kit-only**.
- **Gotcha:** kit option only until the SDoC exists; ship **cell-not-included** ("use any protected 18650"). Real-unit photos are the #1 blocker — you need boards in hand.

### Supporting tactics (turn on this week, they compound)
| # | Tactic | First $ | Per sale | First action |
|---|--------|---------|----------|--------------|
| 4 | **Donation / tip-jar / GitHub Sponsors** on the free hub | 3–10 days | $3–100 | Create Ko-fi + apply for GitHub Sponsors today (Sponsors has a queue); add README badges |
| 5 | **BYO-hardware service tiers** (paid setup call, pay-what-you-want hub download, commercial support) | 3–10 days | $15–150 | Put the hub on Gumroad PWYW; stand up a Calendly + Stripe "Guided Setup — $49" |
| 6 | **Local in-person kit sales** (homelab/maker meetup, brewery, greenhouse) | 1–3 weeks | $39–49 cash | RSVP to the nearest homelab/Home Assistant meetup; set up Square/Stripe Tap-to-Pay |
| 7 | **Sponsorship** (README slot, sponsor-a-feature bounty) | 3–8 weeks | $25–500+ | Tag 2–3 roadmap items (syslog/SNMP, rack grouping) as "sponsorable" with a price |

> **Honest exclusion:** *Selling assembled probes to restaurants* is the eventual high-value sale (~$80–90/probe), but it is **6–12+ weeks out and gated** by rev-2 + FCC SDoC. Don't shortcut it by selling a rev-1 assembled unit. It's where the pilot deposits *convert* — after the respin, not now.

---

## TRACK A — Revenue now (the cash engine)

Rev-1 boards + free software → **DIY kits on Tindie** and **paid restaurant pilots**. No FCC gate, near-zero capital. This validates the *exact same demand* as the future assembled SKU while it gets built.

### A1. DIY kits — from "boards on my doorstep" to "first kit shipped"
Full playbook: **[docs/DIY_KIT.md](DIY_KIT.md)**. Wall-clock to first sale working solo: **~1 focused week** after boards land.

**Before the boxes arrive (do in parallel, no boards needed):**
- [ ] Order non-board parts for a **batch of 10 kits** now (DS18B20 probes + TP4056s are slow from overseas). See BOM in [docs/BOM.md](BOM.md).
- [ ] Set up the flashing PC: `arduino-cli` + ESP32 core + `WiFiManager ArduinoJson OneWire DallasTemperature` + `pyserial esptool`. (`pyserial` lets `firmware/factory_flash.py` auto-capture the label line.)
- [ ] Stand up a bench hub (`Start.sh`, dashboard `http://localhost:8088`) + a test 2.4 GHz Wi-Fi network.
- [ ] Start the batch serial-log CSV (header from [docs/LABEL_TEMPLATE.md](LABEL_TEMPLATE.md)) — one row per board = traceability + support lookup.
- [ ] Build + host the browser-flash page: `./flash/build_merged_bin.sh` → host `flash/` over HTTPS on GitHub Pages. **Don't print the flash QR anywhere until you've flashed a real board from it.**

**When boards land — the gated build flow:**
1. **Incoming QC** ([docs/QC_CHECKLIST.md](QC_CHECKLIST.md)): count vs packing slip; visual-inspect each carrier + SuperMini; power-on smoke-test a sample; quarantine any fail.
2. **Validate the toolchain on ONE board (the gate):** `factory_flash.py`'s FQBN/partition are *documented, not yet hardware-verified*. Run `arduino-cli board details --fqbn esp32:esp32:esp32c3`, flash the first board end-to-end, walk the **full** QC checklist once. Separately flash a *second* board **from the browser page**. Only then unlock batch mode.
3. **Build a test rig** (10 min): fully populate one carrier — mandatory **4.7 kΩ pull-up** (GPIO5↔3V3), female headers, screw terminal — so every unit tests with zero soldering.
4. **Pair-and-test every board (~3–4 min each):** flash *with that kit's DS18B20 connected* — the `probe_id` is derived from the sensor ROM at first boot and persisted in NVS, so this both **catches a dead probe (reads −127 / 85.0 / NaN — the #1 return)** and guarantees the label is correct. Bag the tested probe **with its board** immediately (matched set).
5. **Two tiers** (the audience-doubler): **Maker Kit ~$39** (loose parts, solder-yourself) and **Plug-Together ~$49** (you batch-solder passive headers + screw terminal; buyer just seats the module + powers up — **buyer still completes the radio**, which keeps it FCC-exempt).
6. **Bag, label, card:** label per [docs/LABEL_TEMPLATE.md](LABEL_TEMPLATE.md); print the quick-start card from `docs/kit-quickstart-card.html`; ship **cell-not-included**.
7. **List on Tindie** (see priority-stack #3), set honest **3–5 business day** handling time.

### A2. Restaurant paid pilots — from "text my contact" to "they're paying me"
Full motion: **[docs/PILOT_OFFER.md](PILOT_OFFER.md)** + [docs/GO_TO_MARKET.md](GO_TO_MARKET.md). Target: **first paid site ~45 days.**

`Warm text → 15-min qualifying call → 30-min free install (2–4 loaner probes) → 30 days proving it catches real events → conversion + deposit → referral ask.`

- **Outreach:** a **text**, not an email. Lead with loss, never tech: *"a wireless monitor that texts you the second a walk-in starts drifting overnight, before you open the door to a dead compressor and a lost load — free for 30 days, no contract."*
- **Qualify (15 min):** how many cold units? Ever lost a load (get the $ number)? Who's on-call overnight and how? Always-on PC? Does Wi-Fi reach the walk-in? Who signs off?
- **Install:** cover **walk-in freezer + cooler first**; set **defrost-proof thresholds** (deadband + sustained-duration so a 6-min defrost spike is ignored, a real compressor loss isn't); wire text/Slack alerts to the real overnight phone.
- **The killer demo, live on install day:** unplug a probe and let the **silent-sensor alarm** fire within ~15 min — *"a dark freezer never passes as OK."* Cheap thermometers can't do this.
- **Prove value:** weekly screenshot touch; capture every real event (door-left-open spikes, overnight drift, per-probe min/max/avg telling a coil-icing story).
- **Convert (day 25–30):** recap what it caught → *"software's free forever, no monthly fee, you buy the probes once"* → quote the site package → hand over the written limits.
- **Harden the hardware** for the walk-in (the #1 field-failure zone): mains USB power not battery; probe lead ≤3 m with series resistor + TVS on DQ; strain-relief at the gland; sealed box mounted *outside* the cold zone with only the stainless tip inside; verify Wi-Fi at install; buffer the tip in a glycol bottle to ride through defrost. Detail in [docs/REV2_SCHEMATIC.md](REV2_SCHEMATIC.md) / [docs/PCB_REV2_MODULE.md](PCB_REV2_MODULE.md) / [docs/BOM.md](BOM.md).
- **Referrals** — the compounding engine: ask right after it catches something and at conversion. *"Who else runs a kitchen who'd hate to lose a walk-in? I'll set them up free for 30 days."* Bank a one-line testimonial + one anonymized "what it caught" screenshot — it opens the next three restaurants.

---

## TRACK B — Scale later (gated on Track A proving demand)

Rev-2 respin around the pre-certified **ESP32-C3-MINI-1** module (FCC ID `2AC7Z-ESPC3MINI1`) → cheap **Part 15B SDoC** → sell **assembled** units. Firmware is unchanged. Full guide: **[docs/REV2_BUILD_GUIDE.md](REV2_BUILD_GUIDE.md)**, [docs/REV2_SCHEMATIC.md](REV2_SCHEMATIC.md), [docs/PCB_REV2_MODULE.md](PCB_REV2_MODULE.md).

**The money discipline — design early, spend late:**

| Phase | Work | Calendar | Cash | Gate |
|---|---|---|---|---|
| **A** Design | KiCad schematic + PCB (module + ~10-part support circuit, ERC/DRC clean) | ~1–2 wk part-time | **$0** | **None — start the week rev-1 boards arrive** |
| **B** Export | Gerbers + BOM + CPL (centroid) | ~1 hr | **$0** | **Park here** until a demand signal |
| **C** PCBA | JLCPCB assembles 5–10 (places the SMD module correctly; you hand-solder THT connectors) | ~1–2 wk + ship | **~$150–350** | Firmware proven on rev-1 **+** real interest |
| **D** Bring-up | Smoke-test 3V3 rail, boot test, flash via UART, full QC, confirm radio + probe on-module | ~2–4 days | ~$0 | All QC PASS → certify; any bug → **respin before certifying** |
| **E** FCC SDoC | Part 15B unintentional-radiator test at accredited lab; "Contains FCC ID" label; US responsible party | ~2–4 wk | **~$300–1,500** | **Pilots convert / deposits collected — the hardest gate** |
| **F** Sell assembled | B2B to restaurants (full margin) + homelab USB-C variant on Tindie | ongoing | revenue | LLC + bound insurance + label in place |

**Load-bearing design details (from [docs/REV2_SCHEMATIC.md](REV2_SCHEMATIC.md)):** use a true LDO (ME6211C33M5G / RT9013-33, *not* AMS1117 on battery); **wire the IO8 LED active-low** (`3V3 → R → LED → IO8` + pull-up — the reverse bricks boot); **4.7 kΩ pull-up on IO5** is mandatory; module at the board edge with a **copper-free antenna keep-out** (a condition of the FCC grant transferring); leave IO2 unconnected. Certify the **USB-always-on + UART-header restaurant SKU first** (fewest parts, fewest RF variables, higher-margin target); add the USB-C homelab variant as a second spin.

**Critical-path realism:** from "pilot says yes" to "first legal assembled sale" is **~6–10 weeks and ~$500–2,000** in new spend — *if* Phases A–B were done free in advance. Front-load the free design; gate the two real spends (PCBA, SDoC) behind proven demand.

---

## Unified timeline

### This week (no FCC, ~$100–700, mostly your time)
1. **Form Datum Labs LLC** (home state, $50–500) — it's your liability shield *and* your future FCC responsible party. Get the **EIN free at IRS.gov** (never pay a third party). Open a **business bank account** and run every dollar through it.
2. **Turn on no-inventory revenue:** stand up the Stripe pre-order link, Ko-fi + GitHub Sponsors, and a Gumroad PWYW hub download + paid setup call. These can earn within days.
3. **Edit [docs/WARRANTY.md](WARRANTY.md)** — swap in "Setpoint"/"Datum Labs LLC" + address + real support URL; confirm the liability cap (limits total liability to hardware price, excludes consequential/spoiled-inventory damages, states "monitoring aid, not a certified/HACCP/life-safety device"). Ship it with **every kit and every pilot**.
4. **Pull 2–3 product-liability insurance quotes** (CGL $1M/$2M *with products-completed-operations*, ~$400–1,200/yr). Prep the **W-9**. Register the **home-state sales-tax permit** at first sale.
5. **Order kit parts for 10** and **set up the flashing PC + bench hub** (Track A1 pre-work).
6. **Text your warmest restaurant contact** with the opener; line up the next two (Track A2).
7. **Start the rev-2 KiCad design** — it's free, do it while boards ship (Track B, Phase A).

### Weeks 2–4 (boards land)
1. **Incoming QC → validate the toolchain on one board (the gate) → build the test rig** (Track A1 steps 1–3).
2. **Pair-and-test the batch**; bag/label/card; **shoot the Tindie photos + build one hero unit**; **publish the kit-only Tindie listing.**
3. **Build 2–3 loaner units**; run the **15-min qualifying calls**; **install the first pilot within the week** and do the silent-sensor demo live.
4. **Bind insurance before hardware goes into a commercial kitchen.**
5. **Finish rev-2 design (Phases A–B) and export the Gerber/BOM/CPL package** — then **park it** (Phase B). No further Track-B money yet.

### Month 2–3
1. **Fulfill kit orders** within 3–5 days; carry a few kits to a local meetup for cash sales.
2. **Run the pilots** for 30 days: weekly screenshot touches, capture real events.
3. **Convert pilots (day 25–30):** recap what it caught, quote the site package, **collect a founding-customer deposit / signed intent**, ask for referrals + a testimonial.
4. **If demand is real** (steady kit sales and/or pilot deposits): **order the rev-2 PCBA batch (5–10 units, ~$150–350)** and bring them up (Phases C–D).

### When demand is proven — THE GATE
*Trigger: pilots convert to deposits/signed intent, or Tindie kits sell steadily. Only now spend on certification.*
1. **Run the FCC Part 15B SDoC** (~$300–1,500, 2–4 wks) on a QC-passed rev-2 unit; keep the signed test report on file.
2. **Label every unit** "Contains FCC ID: 2AC7Z-ESPC3MINI1" + the §15.19(a)(3) statement; update [docs/LABEL_TEMPLATE.md](LABEL_TEMPLATE.md).
3. **Confirm insurance is bound; have COI + W-9 ready** for procurement.
4. **Deliver certified rev-2 units** to the reserved pilots (loaner stays in place until you do); **sell assembled** B2B + the homelab variant on Tindie.
5. **Only now consider financing** — and only for *inventory scaling*, never certification. Sequence: **validate → certify → sell → then finance growth.**

---

## Money math

**Per DIY kit** (small batch of ~10, cell not included; ~8% = Tindie 5% + ~3% processing; shipping passed through to buyer):

| Tier | Material COGS | +Labor | Price | Fees | **Gross/kit** | **Margin** |
|---|---|---|---|---|---|---|
| Maker | ~$12.77 | — | **$39** | ~$3.10 | **~$23** | **~59%** |
| Plug-Together | ~$13.07 | ~$2 | **$49** | ~$3.90 | **~$30** | **~61%** |

Both clear the 50–55% target in [docs/BOM.md](BOM.md). Anchor the listing: ~$39 kit vs a $149 Temp Stick, **hub free forever**. Upsell multi-probe (2-probe ~$69, 4-probe ~$129) — per-probe price drops, bagging time barely moves.

**Per restaurant probe / site** (value-anchored to the $2k–10k loss, not the ~$16–22 BOM):

| Package | Probes | Price | ~Gross |
|---|---|---|---|
| Per-probe à la carte | 1 | $89 | ~$70 |
| Essentials (cooler + freezer) | 2 | $179 | ~$140 |
| Standard (+2 reach-ins) | 4 | $329 | ~$255 |
| Full Kitchen | 6 | $479 | ~$370 |

Hub free on their PC; optional pre-configured mini-PC hub +$129–149 (your cost $80–120). No subscription, ever.

**Rev-2 + FCC one-time spend:** PCBA 5–10 units **~$150–350** · SDoC **~$300–1,500** · LLC + a year of insurance **~$450–1,700**. **All-in to legally sell assembled: ~$1,000–3,500.**

**Break-even logic:** you never front the certification. The SDoC (~$300–1,500) is covered by roughly **1–4 Full-Kitchen sales, or ~13–65 kits, or simply the pilot deposits you collect before you spend.** That's the whole point: kits + pilots earn first, and *their* revenue pays for rev-2 and the SDoC. Certification is always funded by demand, never borrowed against hope.

---

## Legal / FCC gate table

Three revenue activities, three different gates. Only one touches the finished-product FCC test — sequence around it and you earn this month. Full detail: **[docs/STARTUP_CHECKLIST.md](STARTUP_CHECKLIST.md)** + [docs/COMPLIANCE.md](COMPLIANCE.md).

| Revenue activity | FCC gate | Legal / insurance gate | Can start |
|---|---|---|---|
| **DIY kits** (buyer assembles the radio; pre-flashing is not assembly) | **None** — you never placed a finished radio on the market | LLC + liability-cap warranty in the box; insurance recommended | **This week** |
| **Restaurant loaner pilots** (free 30-day evaluation) | **None** — a loaner is not a sale or marketing of the device | **Bind insurance before hardware enters a commercial kitchen**; LLC | **This week** |
| **Selling ASSEMBLED units** | **Part 15B SDoC** (~$300–1,500) + **US responsible party** + "Contains FCC ID" label | LLC (*is* the responsible party) + bound insurance + COI + W-9 | **After rev-2 + SDoC** |

**Why rev-1 can't be sold assembled:** it's a *bare* ESP32-C3 chip + trace antenna with no modular grant — selling it finished would owe ~$5k–15k intentional-radiator testing. Rev-2 on the pre-certified module drops you to the cheap SDoC. Until rev-2 exists, you sell **kits and run loaner pilots** — that's the plan, not a limitation.

**The honest disclaimer posture (a legal control, hold it everywhere):** advertise **"±0.5 °C typical, uncalibrated"** (resolution ≠ accuracy). Sell as a **loss-prevention / temperature-logging aid — explicitly NOT a certified, NIST-traceable, or HACCP/health-code compliance instrument**, and state it **does not replace required manual checks or official records**, and that **monitoring stops in a full power outage**. Never claim a certification you don't hold — that's how you manufacture liability you don't have. Stay out of VFC/vaccine, pharma GxP, and EN 12830 cold-chain entirely.

**Sales tax, briefly:** you likely collect/remit **only in your home state** to start (far below other states' ~$100k/200-transaction economic-nexus thresholds). **Tindie collects and remits for you** as a marketplace facilitator — a real reason to lean on it early. Revisit with an accountant only as you approach an out-of-state threshold.

---

## Deeper docs index

- Product & versions: [docs/VERSIONS.md](VERSIONS.md) (Portable vs Fixed)
- Revenue-now execution: [docs/DIY_KIT.md](DIY_KIT.md) · [docs/TINDIE_LISTING.md](TINDIE_LISTING.md) · [docs/LISTING.md](LISTING.md) · [docs/PILOT_OFFER.md](PILOT_OFFER.md) · [docs/PREORDER.md](PREORDER.md) · [docs/GO_TO_MARKET.md](GO_TO_MARKET.md) · [docs/LAUNCH.md](LAUNCH.md) · `docs/roi-calculator.html` (restaurant ROI tool)
- Build, QC & reliability: [docs/QC_CHECKLIST.md](QC_CHECKLIST.md) · [docs/ASSEMBLY.md](ASSEMBLY.md) · [docs/LABEL_TEMPLATE.md](LABEL_TEMPLATE.md) · [docs/BOM.md](BOM.md) · [docs/HUB_RELIABILITY.md](HUB_RELIABILITY.md) · `docs/kit-quickstart-card.html` · `firmware/factory_flash.py` · `flash/`
- Scale-later (rev-2 + FCC): [docs/REV2_BUILD_GUIDE.md](REV2_BUILD_GUIDE.md) · [docs/REV2_SCHEMATIC.md](REV2_SCHEMATIC.md) · [docs/PCB_REV2_MODULE.md](PCB_REV2_MODULE.md) · [docs/PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md)
- Business/legal & readiness: [docs/STARTUP_CHECKLIST.md](STARTUP_CHECKLIST.md) · [docs/COMPLIANCE.md](COMPLIANCE.md) · [docs/WARRANTY.md](WARRANTY.md) · [docs/RETURNS.md](RETURNS.md) · [docs/MATERIALS_AND_NEXT_STEPS.md](MATERIALS_AND_NEXT_STEPS.md)

---

## This week's top 5 do-now list

- [ ] **1. Form Datum Labs LLC + get the free EIN + open a business bank account.** Your liability shield and future FCC responsible party. ($50–500, ~1 hour of forms.)
- [ ] **2. Put up the Stripe pre-order link for the Maker Kit** and post it once to your audience + restaurant contacts. First dollars in 2–5 days, zero inventory.
- [ ] **3. Text your warmest restaurant contact the pilot opener** (and line up two more). Book a 30-min loaner install; the deposit + setup fee is your fastest B2B cash.
- [ ] **4. Order kit parts for 10 and set up the flashing PC + bench hub** so you can build the moment boards land — and edit [docs/WARRANTY.md](WARRANTY.md) with real names + the liability cap to ship in every box.
- [ ] **5. Start the rev-2 KiCad schematic** ([docs/REV2_BUILD_GUIDE.md](REV2_BUILD_GUIDE.md)). It's $0 and can be fully designed and exported before you spend a cent — so the day a pilot converts, you're only ~6 weeks from a certified, sellable unit.
