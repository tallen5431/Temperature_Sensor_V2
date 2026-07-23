# START HERE — Setpoint, by Datum Labs

Your founder's checklist: the whole plan distilled to a dependency-ordered sequence you can tick off.
Deeper detail lives in the linked docs — this is the map and the order. Not legal, tax, or insurance
advice; confirm specifics with an attorney, accountant, and broker before binding money.

> **The one rule that orders everything:** earn from **DIY kits + restaurant loaner pilots first**
> (no FCC gate, near-zero capital), and only spend on the **rev-2 respin + FCC** once that demand is
> real and has funded it. Compliance trails demand — it never blocks the first sale.

**Product recap:** a Wi-Fi temperature probe that reports to a free, local-first hub app you run on your
own PC (no cloud/account/subscription). Two versions — **Portable** (battery, a movable tool) and
**Fixed** (USB always-on, for walk-ins/racks). One board, one firmware. See
[`docs/VERSIONS.md`](docs/VERSIONS.md).

---

## ✅ Do these 3 today (everything else keys off them)

- [ ] **1. Start the Datum Labs LLC filing** and get the free **EIN** at IRS.gov.
- [ ] **2. Buy a domain** and turn on **`support@` / `hello@`** email.
- [ ] **3. Compile the firmware** (no board needed) — proves the toolchain:
  ```
  arduino-cli core install esp32:esp32
  arduino-cli compile --fqbn esp32:esp32:esp32c3 esp32_temp_probe/
  ```

---

## Phase 1 — This week (no boards needed · ~$100–700)

Ordered by dependency — each unblocks the next.

- [ ] **Form the LLC → EIN → business bank account.** First, because your bank, Stripe payouts, and
      FCC "responsible party" all depend on it. → [`docs/STARTUP_CHECKLIST.md`](docs/STARTUP_CHECKLIST.md)
- [ ] **Register the domain + `support@`.** Unblocks every shipping doc — then one find-replace swaps
      each `example.com/support` placeholder. Do this before printing a label or publishing a listing.
- [ ] **USPTO knockout search** on "Setpoint" (Class 9) + "Datum Labs" at uspto.gov. If it's crowded,
      rename before printing brand stock.
- [ ] **Install the flash toolchain + compile** (today's action #3). Only the *upload* step later needs
      a board.
- [ ] **Order kit parts for 10** — DS18B20 probes + TP4056s are the 2–4-week long-lead items, order now;
      add a small fast Amazon backup of each. → [`docs/MATERIALS_AND_NEXT_STEPS.md`](docs/MATERIALS_AND_NEXT_STEPS.md), [`docs/BOM.md`](docs/BOM.md)
- [ ] **Set up the bench hub** (`Start.sh` → dashboard on `:8088`) + a 2.4 GHz test Wi-Fi network.
- [ ] **Stand up the Stripe pre-order link** ($15 refundable deposit) and post it once (README banner +
      r/homelab + your contacts). → [`docs/PREORDER.md`](docs/PREORDER.md)
- [ ] **Text your warmest restaurant contact** the pilot opener; line up two more. → [`docs/PILOT_OFFER.md`](docs/PILOT_OFFER.md)
- [ ] **Pull 2–3 product-liability insurance quotes** (CGL $1M/$2M + products). You bind before the
      first kitchen install, not now.
- [ ] **Edit [`docs/WARRANTY.md`](docs/WARRANTY.md) + [`docs/RETURNS.md`](docs/RETURNS.md)** with the LLC
      name + real support URL; confirm the liability cap. Ships in every kit and pilot.

---

## Phase 2 — When the boards arrive (weeks 2–4)

- [ ] **Incoming QC → flash ONE board end-to-end and walk the full checklist once** (the real toolchain
      gate), then flash a second board from the browser page. Only then batch-flash. → [`docs/QC_CHECKLIST.md`](docs/QC_CHECKLIST.md)
- [ ] **Build the no-solder test rig, then pair-and-test every board** — include the **ice-bath 0 °C
      check** (QC 5.3) so "verified" is earned. Bag each tested probe with its board.
- [ ] **Restaurant pilot:** build 2–3 **Fixed (USB)** loaners → **bind insurance** → install using
      [`docs/HUB_RELIABILITY.md`](docs/HUB_RELIABILITY.md) → do the silent-sensor demo live → show the
      payback with `docs/roi-calculator.html`.
- [ ] **Kits:** shoot the photos (the #1 Tindie blocker) → publish the **kit-only** listing with both
      **Portable** and **Fixed** options. → [`docs/TINDIE_LISTING.md`](docs/TINDIE_LISTING.md)
- [ ] **Rev-2 (free part):** finish the KiCad schematic + export Gerber/BOM/CPL, then **park it.** →
      [`docs/REV2_BUILD_GUIDE.md`](docs/REV2_BUILD_GUIDE.md)

---

## Phase 3 — Month 2–3

- [ ] Fulfill kits (3–5 day handling); run pilots 30 days and **capture every event they catch.**
- [ ] **Convert pilots** (day 25–30): deposit + referral ask + a one-line testimonial.
- [ ] **If demand is real** → order the rev-2 PCBA batch (~$150–350) and bring it up.

---

## The gate — only after demand is proven

- [ ] Run the **FCC Part 15B SDoC** (~$300–1,500) on a QC-passed rev-2 unit; keep the signed report.
- [ ] Label **"Contains FCC ID: 2AC7Z-ESPC3MINI1"**; confirm insurance bound; COI + W-9 ready.
- [ ] **Sell assembled units** (restaurants B2B + a homelab variant). Finance only for inventory
      scaling — never certification.

---

## Which doc for what

| I want to… | Go to |
|---|---|
| See the whole plan / money math | [`docs/ACTION_PLAN.md`](docs/ACTION_PLAN.md) · `docs/action-plan.html` |
| Buy materials + readiness gates + gaps | [`docs/MATERIALS_AND_NEXT_STEPS.md`](docs/MATERIALS_AND_NEXT_STEPS.md) |
| Launch the pre-order | [`docs/PREORDER.md`](docs/PREORDER.md) |
| Run a restaurant pilot / show ROI | [`docs/PILOT_OFFER.md`](docs/PILOT_OFFER.md) · `docs/roi-calculator.html` |
| Build + QC kits | [`docs/DIY_KIT.md`](docs/DIY_KIT.md) · [`docs/QC_CHECKLIST.md`](docs/QC_CHECKLIST.md) · [`docs/LABEL_TEMPLATE.md`](docs/LABEL_TEMPLATE.md) |
| Keep a pilot hub running | [`docs/HUB_RELIABILITY.md`](docs/HUB_RELIABILITY.md) |
| List on Tindie | [`docs/TINDIE_LISTING.md`](docs/TINDIE_LISTING.md) · [`docs/LISTING.md`](docs/LISTING.md) |
| Understand the two versions | [`docs/VERSIONS.md`](docs/VERSIONS.md) |
| Design/order rev-2 + certify | [`docs/REV2_BUILD_GUIDE.md`](docs/REV2_BUILD_GUIDE.md) · [`docs/STARTUP_CHECKLIST.md`](docs/STARTUP_CHECKLIST.md) |
