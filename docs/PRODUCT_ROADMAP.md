# TempSensor — Product Roadmap (what to do with what exists)

> The single "what next" doc. Ties together the strategy ([`GO_TO_MARKET.md`](GO_TO_MARKET.md)),
> the launch runbook ([`LAUNCH.md`](LAUNCH.md)), the legal/cost sequence
> ([`STARTUP_CHECKLIST.md`](STARTUP_CHECKLIST.md)), the pilot tool ([`PILOT_OFFER.md`](PILOT_OFFER.md)),
> and the two board revisions ([`PCB_REV2_MODULE.md`](PCB_REV2_MODULE.md) /
> [`REV2_BUILD_GUIDE.md`](REV2_BUILD_GUIDE.md)).

---

## Where you are today (honest snapshot)

- ✅ **Software:** hardened, tested, free, local-first (hub + firmware + integrations + docs).
- ✅ **Landing page:** restaurant-facing, claims verified — ready to show contacts.
- ✅ **Rev-1 PCBs:** 50 boards ordered (bare-chip SuperMini). **Great for pilots, dev, and DIY kits;
  NOT sellable as assembled units** (no modular FCC grant).
- ⏭️ **Not yet:** LLC, insurance, FCC SDoC, rev-2 (module) board, first paying customer.

**The gap to revenue is business/ops, not more code.** The product is ready; the next moves are
validation, one legal gate, and one board respin.

---

## The path forward (four phases — walk them in order)

### Phase 0 — Set up the shell (this week, ~$100–700)
Form the **LLC**, get a free **EIN**, open a **business bank account**, and get
**product-liability insurance** quotes. Details + costs in [`STARTUP_CHECKLIST.md`](STARTUP_CHECKLIST.md).
No FCC needed yet.

### Phase 1 — Validate for ~$0, two fronts in parallel
1. **Restaurant pilots (your warm edge).** Hand-build 2–3 rev-1 units, flash + QC
   (`firmware/factory_flash.py`, `docs/QC_CHECKLIST.md`), and run **free 30-day loaner pilots** with
   your contacts using [`PILOT_OFFER.md`](PILOT_OFFER.md). These are evaluations, not sales — clean
   on FCC. Goal: proof they'll pay.
2. **DIY kits on Tindie (homelab crowd).** List the kit (see below), post build-in-public to
   r/homelab / r/selfhosted / Home Assistant forums. Kits sidestep finished-product FCC and cost ~$0.

**Decision gate:** real deposits/intent from a few restaurants, or kit sales + "take my money"
replies. If yes → Phase 2. If not → fix the pitch *before* spending on FCC or a respin.

### Phase 2 — Certify + rev-2 (only once demand is real)
Respin the board to the pre-certified **ESP32-C3-MINI-1** ([`REV2_BUILD_GUIDE.md`](REV2_BUILD_GUIDE.md)),
order a small **JLCPCB PCBA** batch, get the **FCC Part 15B SDoC** (~$300–1,500), and label
"Contains FCC ID: 2AC7Z-ESPC3MINI1." Now sell **assembled** units — direct/B2B to restaurants (full
margin) and assembled homelab units on Tindie.

### Phase 3 — Scale (after ~10+ real sales)
Bigger batches (per-unit cost drops), add a per-unit **calibration option** (~$140) for food-service
buyers who ask, consider **MSP/VAR** channels. A **loan** enters only here — for *inventory*, not
certification. EU/UK is a separate, later decision ([`COMPLIANCE.md`](COMPLIANCE.md)).

---

## The two SKUs (one board family, two products)

| | **DIY Kit** (now, rev-1) | **Assembled Unit** (Phase 2, rev-2) |
|---|---|---|
| Who | Homelab / makers (Tindie) | Restaurants (direct) + homelab (Tindie) |
| Board | Rev-1 SuperMini carrier | Rev-2 module board |
| FCC | Buyer assembles → sidesteps it | Part 15B SDoC required |
| Price | **~$39** | **~$69** (or per-kitchen quote) |
| Margin | High (no assembly labor) | High (~$16–22 BOM) |
| Effort for you | Bag parts, print card | JLC PCBA + hand-solder + QC |

---

## How to do the DIY kit (rev-1, sellable now)

**What goes in the bag:**
- 1× rev-1 carrier PCB (from your batch of 50).
- 1× ESP32-C3 SuperMini (you're reselling a dev board — the buyer assembles it).
- 1× DS18B20 waterproof probe.
- 1× 4.7 kΩ resistor + the header/connector parts.
- 1× TP4056 charger + 18650 holder (state clearly whether an 18650 cell is included — shipping
  lithium cells has carrier rules; many kits ship **without** the cell).
- 1× slide switch.
- 1× printed quick-start card with a **QR to your browser-flash page** (ESP Web Tools) + a link to
  `docs/USER_MANUAL.md` and `docs/ASSEMBLY.md`.

**Why this is the right first product:**
- **Kits sidestep finished-product FCC** — the buyer builds the radio device, not you. *(Keep it a
  genuine solder-it-yourself kit; if you scale kits, confirm the current FCC kit rules with a
  consultant.)*
- **Near-zero capital** — bag by hand, no assembly labor, no inventory risk beyond parts.
- **Your browser-flash page removes the scary part** — the buyer flashes firmware from Chrome in one
  click, no toolchain. That's a genuine differentiator; lead the listing with it.

**Make it convert:**
- **Pre-flash the SuperMini** before bagging (flashing ≠ assembly, so this is fine and adds value —
  the buyer just solders and goes).
- **Real photos of a built unit** — Tindie listings live or die on photos. This needs one hand-built
  unit, which you're doing for pilots anyway.
- Paste the ready listing copy from [`TINDIE_LISTING.md`](TINDIE_LISTING.md); price the kit ~$39.
- Ship with the QR + a one-page assembly card (point to `docs/ASSEMBLY.md`).

---

## What makes the *assembled* unit possible (rev-2 parts)

You can only sell **fully assembled** on the **rev-2 board**, and the linchpin part is the
**pre-certified `ESP32-C3-MINI-1` module** (FCC ID `2AC7Z-ESPC3MINI1`) — its modular grant is what
lets a finished unit take the cheap Part 15B SDoC instead of a $5–15k full test. The complete rev-2
parts list (module + LDO + support circuit + connectors) and the KiCad/JLC build steps are in
[`REV2_BUILD_GUIDE.md`](REV2_BUILD_GUIDE.md).

---

## The 30-second version

**Rev-1 boards → DIY kits + free restaurant pilots (validate, ~$0). If they pay → LLC + rev-2 module
board + FCC SDoC → sell assembled (restaurants direct, homelab on Tindie). Loan only later, for
inventory.** You're one validation loop and one board respin from a real product.
