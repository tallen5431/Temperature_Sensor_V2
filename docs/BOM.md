# TempSensor — Bill of Materials (BOM)

This is the parts list to build **one** TempSensor unit — the rechargeable,
battery-powered wireless sensor that pairs with a TempSensor install. Pin
assignments referenced here come from `firmware/src/protocol.h` (the single
source of truth); see [ASSEMBLY.md](ASSEMBLY.md) for the wiring. The shipping
firmware is the sketch `esp32_temp_probe/esp32_temp_probe.ino`.

- **Firmware target:** ESP32-WROOM-32 / -32E, firmware **v2.4.0**, protocol v1.
- **Sensor:** DS18B20 (waterproof probe) on **GPIO5** with a 4.7 kΩ pull-up to
  3V3. This is the **only** sensor the current firmware supports.
- **Status LED:** GPIO2 (`LED_BUILTIN`; on most dev boards the on-board LED, so
  an external LED is optional if you use a bare dev board).
- **Power:** rechargeable-lithium battery. The firmware deep-sleeps between
  readings (idle <1 mA), so a single lithium cell gives long runtime; USB-C is
  used for charging and flashing.
- **Future / not in current firmware:** MAX31855 K-type thermocouple (SPI) and
  SHT4x temp+humidity (I2C) are documented as possible future variants only.
  They are **not** implemented in v2.4.0 and are not populated on shipping units.

---

## Core build (DS18B20, one unit)

| # | Component | Spec / part example | Qty | Example supplier | Unit cost (USD) |
|---|-----------|---------------------|-----|------------------|-----------------|
| 1 | ESP32 dev board | ESP32-WROOM-32E DevKitC (38-pin), USB-C | 1 | DigiKey 1965-ESP32-DEVKITC-32E-ND / Amazon | 6.50 |
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

**Core per-unit material cost ≈ $22.19** (round to **~$22.20**).
Buying dev boards, probes, and cells in 10+ qty typically drops this to
**~$16–18/unit**.

> The DS18B20 is a 1-Wire part and **requires** the 4.7 kΩ pull-up (item 3) — the
> bus will not read without it.

### Future / experimental sensor variants (NOT in current firmware)

The MAX31855 K-type thermocouple and SHT4x temp+humidity options that earlier
docs described are **not implemented in firmware v2.4.0** — there is no build
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
| DS18B20 (standard, battery) | ~$22.20 | ~$8 (≈20 min @ $24/hr) | ~$30.20 | **$65** | ~54% |

Notes on pricing:
- These are *single-unit maker* numbers. At batch scale (parts in 10s–100s,
  jigged flashing/test) landed cost drops materially and you can either widen
  margin or cut retail toward ~$49.
- TempSensor is the free local-first software; the TempSensor hardware is the
  revenue item. One hub can serve many probes, so upsell is additional probes.
- The thermocouple / humidity variants are not priced here because they are not
  yet supported by the firmware (see above).

---

## Battery, waterproofing & food-safe notes

- **Battery:** use a single protected lithium cell with the TP4056 charge/protect
  board (items 6–8). The board handles USB-C charging and over-discharge cut-off;
  never charge a bare unprotected cell. Keep the cell inside the sealed enclosure,
  away from the probe gland and any moisture path.
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
