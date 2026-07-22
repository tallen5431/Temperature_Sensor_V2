# Setpoint — Bill of Materials (BOM)

This is the parts list to build **one** Setpoint unit. Setpoint ships in **two versions** that share
this same board, probe, and firmware image — only the power block differs: **Portable** (battery,
deep-sleep) and **Fixed** (USB, always-on, no battery). See [`VERSIONS.md`](VERSIONS.md) for which to
build and why. Pin assignments referenced here come from `firmware/src/protocol.h`; see
[ASSEMBLY.md](ASSEMBLY.md) for the wiring. The shipping firmware is the sketch
`esp32_temp_probe/esp32_temp_probe.ino`.

> **Board:** the rev-1 unit is the **ESP32-C3 SuperMini** (USB-C native). The firmware now targets it —
> the status LED is auto-selected to **GPIO8, active-low** when built for the C3 (it falls back to a
> WROOM's GPIO2 active-high for that board), and GPIO8 is kept boot-safe (it's a strapping pin held
> high at reset). DS18B20 stays on **GPIO5 + 4.7 kΩ pull-up**. Build/flash with FQBN
> `esp32:esp32:esp32c3`.

- **Firmware target:** ESP32-C3 (SuperMini), firmware **v2.7.0**, protocol v1 (FQBN `esp32:esp32:esp32c3`).
- **Sensor:** DS18B20 (waterproof probe) on **GPIO5** with a 4.7 kΩ pull-up to
  3V3. This is the **only** sensor the current firmware supports.
- **Status LED:** GPIO8 (the C3 SuperMini's on-board LED, **active-low**), so no external LED is
  needed. The firmware drives it boot-safe (GPIO8 is a strapping pin, held high at reset).
- **Power (version-dependent — see [`VERSIONS.md`](VERSIONS.md)):** **Portable** runs on a protected
  lithium cell and deep-sleeps between readings (idle <1 mA) for long runtime (USB-C for charging +
  flashing). **Fixed** runs **always-on from USB-C with no battery** (fewer parts, no lithium).
- **Future / not in current firmware:** MAX31855 K-type thermocouple (SPI) and
  SHT4x temp+humidity (I2C) are documented as possible future variants only.
  They are **not** implemented in v2.7.0 and are not populated on shipping units.

---

## Core build (DS18B20, one unit)

| # | Component | Spec / part example | Qty | Example supplier | Unit cost (USD) |
|---|-----------|---------------------|-----|------------------|-----------------|
| 1 | ESP32-C3 dev board | ESP32-C3 SuperMini (USB-C native, on-board LED GPIO8) | 1 | Amazon B0DFWG87JS / AliExpress | 3.50 |
| 2 | DS18B20 waterproof probe | Stainless tube, 1 m lead, 3-wire (VDD/GND/DQ) | 1 | Adafruit #381 / Amazon | 3.50 |
| 3 | Pull-up resistor | 4.7 kΩ, 1/4 W, ±5% (DS18B20 DQ → 3V3) | 1 | any (buy a strip) | 0.02 |
| 4 | Status LED | 3 mm or 5 mm, any color (skip if using on-board LED) | 1 | any | 0.05 |
| 5 | LED series resistor | 330 Ω, 1/4 W (only if using an external LED) | 1 | any | 0.02 |
| 6 | Rechargeable lithium cell | 18650 Li-ion ~2500 mAh (or a LiPo pack, 3.7 V nominal) | 1 | any reputable brand | 4.00 |
| 7 | Charge + protection board | TP4056 with battery protection (USB-C in, 3.7 V Li-ion) | 1 | any | 0.60 |
| 8 | Battery holder / connector | 18650 holder, or JST-PH pigtail for a LiPo | 1 | any | 0.60 |
| 9 | USB-C cable + charger | 5 V / ≥500 mA USB-C source (charging + flashing) | 1 | any | 3.50 |
| 10 | Enclosure | ABS project box ~65×50×25 mm, with cable gland / grommet for strain relief | 1 | Hammond 1551 / Amazon | 2.50 |
| 11 | Cable gland / strain relief | PG7 nylon gland OR rubber grommet + zip-tie anchor | 1 | any | 0.30 |
| 12 | Hookup wire / header | Dupont jumpers or 22 AWG solid, plus 0.1" header if socketing | small | any | 0.20 |
| 13 | Misc (solder, heatshrink, standoffs) | consumables, amortized per unit | — | — | 0.40 |

**Core per-unit material cost ≈ $19.19** (round to **~$19.20**) for the **Portable** build (the C3
SuperMini is ~$3 cheaper than the old DevKitC). Buying probes, boards, and cells in 10+ qty typically
drops this to **~$13–15/unit**.

> **Version split (see [`VERSIONS.md`](VERSIONS.md)):** items **6–8 (lithium cell, TP4056 charge
> board, holder) plus a slide on/off switch (~$0.35)** are **Portable-only**. The **Fixed** version
> omits all of them and instead uses a **USB-C wall adapter (~$4)** — so a Fixed unit costs roughly
> **$5 less** in materials and carries **no lithium**. Kits ship **cell-not-included** either way.

> The DS18B20 is a 1-Wire part and **requires** the 4.7 kΩ pull-up (item 3) — the
> bus will not read without it.

### Future / experimental sensor variants (NOT in current firmware)

The MAX31855 K-type thermocouple and SHT4x temp+humidity options that earlier
docs described are **not implemented in firmware v2.7.0** — there is no build
flag or code path for them in `esp32_temp_probe.ino`. Building either variant
would require new firmware first. They are recorded here only as future R&D
reference (parts, not costed into shipping units):

- **MAX31855 + K-type thermocouple (SPI):** high-temp / fast-response probe.
  Would need SPI pins (SCK GPIO18, MISO/SO GPIO19) and a relocated CS — GPIO5,
  its old CS pin, is now the DS18B20 data pin.
- **SHT4x (I2C):** temperature **+ humidity** for hub-computed VPD (grow tents).
  Digital I2C part (SDA GPIO21, SCL GPIO22); needs no 4.7 kΩ pull-up and no
  waterproof probe, and must sit in vented free air.

---

## Suggested retail pricing

Pricing assumes small-maker assembly (hand-soldered, flashed, tested) and a
target gross margin around 50–55% to cover labor, test time, returns, packaging,
the battery, and the printed unit label/QR.

| Build | Material cost | Assembly + test (labor) | Suggested landed cost | **Suggested retail** | Gross margin |
|-------|---------------|--------------------------|-----------------------|----------------------|--------------|
| **Portable** (DS18B20, battery) | ~$19.20 | ~$8 (≈20 min @ $24/hr) | ~$27.20 | **$65** | ~58% |
| **Fixed** (DS18B20, USB, no battery) | ~$14.50 | ~$7 | ~$21.50 | **$55** | ~61% |

> These are *assembled-unit* maker prices (post-FCC). Today rev-1 sells as **DIY kits** at **$39 / $49**
> ([`DIY_KIT.md`](DIY_KIT.md)) — the Fixed (no-battery) kit is the cheaper option to list alongside the
> Portable one.

Notes on pricing:
- These are *single-unit maker* numbers. At batch scale (parts in 10s–100s,
  jigged flashing/test) landed cost drops materially and you can either widen
  margin or cut retail toward ~$49.
- Setpoint is the free local-first software; the Setpoint hardware is the
  revenue item. One hub can serve many probes, so upsell is additional probes.
- The thermocouple / humidity variants are not priced here because they are not
  yet supported by the firmware (see above).

---

## DIY kit COGS & margin (buyer-assembled, board-only)

This is the **actual DIY kit** as it currently ships — distinct from the *assembled* pricing above.
The buyer solders the rev-1 carrier PCB + modules and **flashes it themselves** in the browser
([`DIY_KIT.md`](DIY_KIT.md)). It's **board-only** (no enclosure), the **18650 cell is not included**
(lithium carrier rules; the buyer sources a good cell), and the **DS18B20 ships with the JST-PH
pre-terminated** so there's no crimping. Costs are at ~10-qty buying and drop further in 50s–100s.

### Per-kit cost

| Part | ~Cost (qty 10) |
|---|---|
| Carrier PCB (custom) | 1.75 |
| ESP32-C3 SuperMini | 3.00 |
| DS18B20 waterproof probe, JST-PH pre-terminated | 3.75 |
| 4.7 kΩ pull-up resistor | 0.02 |
| TP4056 charge/protect module | 0.60 |
| SPDT slide switch | 0.35 |
| 18650 holder | 0.60 |
| Header pins (2 rows + spares) | 0.15 |
| JST-PH board connector | 0.20 |
| USB-C **data** cable (USB-C→USB-A) | 1.75 |
| **Parts subtotal** | **~$12.17** |
| Anti-static bag + parts baggies | 0.50 |
| Printed quick-start card + serial/QR label | 0.65 |
| Mailer / packaging | 0.75 |
| **Landed COGS (excl. postage & fees)** | **~$14.07** |

> Bundle a **guaranteed data cable**, not a charge-only one — a charge-only cable is the #1 cause of
> "the flasher can't see my board," so the whole point of including it is to kill that support ticket.

> **Not in the kit:** the 18650 cell and an **enclosure** (open-board kit). Ship *cell-not-included*
> (carrier rules + liability on loose lithium) but tell the buyer **exactly** what to add so the kit
> still feels complete: **one reputable 18650, ~2500–3500 mAh, flat-top or protected** (the TP4056
> provides protection either way) from a name brand — and **warn against "9900 mAh"-type
> counterfeits**. This "buy this one cell" line belongs on the quick-start card and in the listing.

### Margin at a few price points

Assumes **~8% all-in marketplace fees** (5% Tindie + ~3% payment processing — confirm current Tindie
payout terms), a **4% returns/defect allowance**, and **buyer-paid shipping** (subtract ~$5 if you
offer free domestic shipping). *After labor* books ~8 min/kit of bagging + probe test + labeling at
~$24/hr (≈$3.20); a solo maker may not cash-count that.

| Price | Fees (8%) | COGS | Returns (4%) | **Contribution** | (after labor) |
|---|---|---|---|---|---|
| **$39** | −3.12 | −14.07 | −1.56 | **$20.25 (52%)** | $17.05 (44%) |
| **$44** | −3.52 | −14.07 | −1.76 | **$24.65 (56%)** | $21.45 (49%) |
| **$49** | −3.92 | −14.07 | −1.96 | **$29.05 (59%)** | $25.85 (53%) |

**Suggested: launch at $39, raise to $44–49 with traction.** Even with the bundled data cable, $39
still clears ~52% contribution before labor — and a low intro price buys the first few reviews that
make every later sale easier (a new Tindie listing lives or dies on social proof). Raise once you
have reviews. Confirm against your real first-batch invoices before locking the price.

---

## Power, waterproofing & food-safe notes

- **Battery (Portable version only):** use a single protected lithium cell with the TP4056
  charge/protect board (items 6–8). The board handles USB-C charging and over-discharge cut-off;
  never charge a bare unprotected cell. Keep the cell inside the sealed enclosure,
  away from the probe gland and any moisture path. The **Fixed** version has no cell — it runs from a
  USB-C wall adapter, so none of these battery cautions apply to it.
- The **stainless DS18B20 probe tip is the only part rated for immersion.** The
  ESP32, resistor, LED, and battery live inside the enclosure and must stay dry.
- For fridge / freezer / fermentation: the stainless probe tip is food-contact
  safe for **incidental contact** (e.g. dangling in a fermentation vessel or
  clipped inside a fridge). For **submerged food-safe** use (in-liquid, extended),
  sheath the tip in food-grade silicone or a thermowell and keep the epoxy joint
  out of the product.
- Seal the cable entry with the gland/grommet (item 11) so condensation and
  wash-down don't wick into the box. Add a bead of neutral-cure (non-acetic)
  silicone around the gland for freezer/greenhouse humidity.
- Provide **strain relief** on the probe lead (cable gland or an internal zip-tie
  anchor) so pulling the cable never stresses the solder joints. This is the #1
  field-failure cause.
- Keep the DS18B20 lead reasonably short (≤3 m) for reliable OneWire timing; the
  4.7 kΩ pull-up (item 3) is mandatory — the bus will not read without it.
