# TempSensor — Startup Checklist (LLC · Insurance · FCC · Costs · Order of Operations)

> **Not legal, tax, or financial advice.** A practitioner's checklist with rough 2026 US costs to
> turn hand-built boards into a business you can sell from. Confirm specifics with an accountant,
> an insurance broker, and an FCC test lab. Deep detail on certification lives in
> [`COMPLIANCE.md`](COMPLIANCE.md); market strategy in [`GO_TO_MARKET.md`](GO_TO_MARKET.md).

---

## ⚠️ Read this first — the FCC gotcha that changes everything

Your board uses an **ESP32-C3 "SuperMini."** Most SuperMini boards are a **bare ESP32-C3 chip with a
PCB trace antenna — NOT a pre-certified radio module.** This matters enormously:

- **If the SuperMini carries a pre-certified module** (has its own **FCC ID** printed on it, e.g. an
  `ESP32-C3-MINI-1`), the intentional-radiator approval carries over and you only need the cheap
  **Part 15B SDoC** (~$300–1,500) — the good path this whole checklist assumes.
- **If it's a bare chip + trace antenna** (the common, cheap case), that approval **does NOT carry
  over.** You'd owe **full intentional-radiator FCC testing** (like a full FCC ID: **~$5,000–15,000+**)
  — a non-starter for a small batch.

**Action:** Before rev 2, either (a) confirm your exact SuperMini has an FCC-ID'd module, or —
better and cheaper — **respin the board around a pre-certified module** (`ESP32-C3-MINI-1` or
`ESP32-C3-WROOM-02`). Same chip, same firmware, same pinout footprint work — but it keeps you on the
$300–1,500 SDoC path instead of a five-figure filing. **This is the single most important
manufacturing decision you have left.**

---

## The costs, at a glance (rough US ranges)

| Item | When | Rough cost | Notes |
|---|---|---|---|
| **LLC formation** | Now | **$50–500** | State filing fee; varies widely by state. |
| **Registered agent** | Now | **$0–150/yr** | Be your own, or pay a service. |
| **EIN (tax ID)** | Now | **Free** | Direct from IRS.gov — never pay a third party for this. |
| **Business bank account** | Now | **$0–15/mo** | Keeps personal/business money separate (protects the LLC shield). |
| **Product-liability insurance** (CGL $1M/occ, $2M agg + products) | Before selling | **~$400–1,200/yr** | Get broker quotes. B2B buyers ask for a Certificate of Insurance (COI). |
| **W-9** | Before B2B sales | **Free** | Restaurants/procurement will request one. |
| **FCC Part 15B SDoC** (finished unit, **assuming a pre-certified module**) | Before selling assembled units | **~$300–1,500** | Simple single-radio build; 2–4 weeks at an accredited lab. See the gotcha above. |
| **FCC labeling** | Before selling assembled units | **~$0** | "Contains FCC ID: [module]" + §15.19(a)(3) statement on each unit. |
| **Per-unit calibration option** (food-service upsell) | Optional / later | **~$140/unit** | Outsourced 3-point accredited cert; only when a buyer asks. |
| **PCB (you've done this)** | — | **~$1/board @ 50** | Bare boards; you hand-solder the 5 parts. |
| **Per-unit material (BOM)** | Per unit | **~$16–22** | Per [`BOM.md`](BOM.md); drops at 10+ qty. |

**Bottom line to get legally sellable (assembled):** roughly **$1,000–3,500 all-in** for LLC +
insurance + FCC SDoC — *if* you're on a pre-certified module. **$0** to start with loaner pilots and
DIY kits.

---

## Order of operations (walk it top to bottom)

### Phase 0 — Set up the shell (this week, ~$100–700, no FCC needed)
- [ ] **Form the LLC** in your state (or use a service). This becomes your FCC "US responsible party."
- [ ] **Get an EIN** free from IRS.gov.
- [ ] **Open a business bank account**; run all business money through it (don't pierce the LLC shield).
- [ ] **Get product-liability insurance quotes** (CGL $1M/$2M + products). You may not bind it until
      you sell, but have the number and a COI ready — procurement asks.
- [ ] Keep your warranty's **liability cap** ([`WARRANTY.md`](WARRANTY.md)) intact — LLC + insurance +
      liability cap are your three shields when selling into food service.

### Phase 1 — Validate for ~$0 (loaner pilots, pre-FCC)
- [ ] Hand-build 2–3 units from your first PCB batch; flash + QC with `firmware/factory_flash.py`
      and [`QC_CHECKLIST.md`](QC_CHECKLIST.md).
- [ ] Run **loaner / evaluation pilots** with your restaurant contacts using
      [`PILOT_OFFER.md`](PILOT_OFFER.md). These are evaluations, **not sales** — that keeps you clean
      on FCC while you learn whether they'll pay.
- [ ] In parallel, list a **DIY kit** (bag of parts) on Tindie and post build-in-public to r/homelab
      / Home Assistant forums — kits sidestep finished-product FCC and cost ~$0 to try.
- [ ] **Decision gate:** do pilots convert to "yes, I'd buy this"? Do you have deposits or signed
      intent from a few restaurants? If yes → Phase 2. If no → fix the pitch before spending on FCC.

### Phase 2 — Clear the gate, then sell assembled (once demand is real)
- [ ] **Resolve the module question** (see gotcha) — respin to a pre-certified module if needed.
- [ ] **FCC Part 15B SDoC** on the finished unit at an accredited lab; keep the signed report.
- [ ] **Label** each unit: "Contains FCC ID: [module ID]" + the §15.19(a)(3) statement.
- [ ] Sell **assembled** units — direct/B2B to restaurants (full margin), homelab assembled on Tindie.
- [ ] Ship with per-unit serial + the audit trail you already have (both help B2B procurement).

### Phase 3 — Scale (only after ~10+ real sales)
- [ ] Larger PCB + parts batch (per-unit cost drops).
- [ ] Add the **calibration option** (~$140/unit) for food-service buyers who ask.
- [ ] Consider **MSP/VAR** channels (recurring monitoring — strong fit for the no-cloud angle).
- [ ] Only now consider a **loan** — for *inventory*, not for certification (which revenue should
      cover by this point). EU/UK is a separate, later decision ([`COMPLIANCE.md`](COMPLIANCE.md) §3).

---

## On taking a loan — sequence it right

- **Do NOT borrow to fund certification before you've validated demand.** The FCC SDoC is small
  ($300–1,500 on the right module); revenue or modest savings should cover it after pilots convert.
- **A loan's job is inventory scaling** once orders are real — an SBA microloan or a business line of
  credit fits then. Borrowing pre-validation is the classic way to end up in debt with a garage full
  of unsold boards.
- The honest sequence is **validate → certify → sell → then finance growth**, not the reverse.
