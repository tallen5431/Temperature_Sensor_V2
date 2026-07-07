# ThermaProbe — Bill of Materials (BOM)

This is the parts list to build **one** ThermaProbe unit — the hardware sensor
that pairs with a ThermaHub install. Pin assignments referenced here come from
`firmware/src/protocol.h` (the single source of truth); see
[ASSEMBLY.md](ASSEMBLY.md) for the wiring.

- **Firmware target:** ESP32-WROOM-32 / -32E, firmware v2.0.0, protocol v1.
- **Default sensor:** DS18B20 (waterproof probe) on GPIO4 with a 4.7 kΩ pull-up to 3V3.
- **Status LED:** GPIO2 (on most dev boards this is the on-board LED, so an
  external LED is optional if you use a bare dev board).
- **Optional sensor:** MAX31855 + K-type thermocouple (SPI) for high-temp /
  probe-abuse builds. Only populated when firmware is built with `-D SENSOR_MAX31855`.
- **Optional sensor:** SHT4x temperature **+ humidity** (I2C) for the humidity/VPD
  "grow" variant. Only populated when firmware is built with `-D SENSOR_SHT4x`.

---

## Core build (DS18B20, one unit)

| # | Component | Spec / part example | Qty | Example supplier | Unit cost (USD) |
|---|-----------|---------------------|-----|------------------|-----------------|
| 1 | ESP32 dev board | ESP32-WROOM-32E DevKitC (38-pin), USB-C | 1 | DigiKey 1965-ESP32-DEVKITC-32E-ND / Amazon | 6.50 |
| 2 | DS18B20 waterproof probe | Stainless tube, 1 m lead, 3-wire (VDD/GND/DQ) | 1 | Adafruit #381 / Amazon | 3.50 |
| 3 | Pull-up resistor | 4.7 kΩ, 1/4 W, ±5% (DS18B20 DQ → 3V3) | 1 | any (buy a strip) | 0.02 |
| 4 | Status LED | 3 mm or 5 mm, any color (skip if using on-board LED) | 1 | any | 0.05 |
| 5 | LED series resistor | 330 Ω, 1/4 W (only if using an external LED) | 1 | any | 0.02 |
| 6 | USB-C cable + power | 5 V / ≥500 mA USB wall adapter + USB-C data cable | 1 | any | 3.50 |
| 7 | Enclosure | ABS project box ~65×50×25 mm, with cable gland / grommet for strain relief | 1 | Hammond 1551 / Amazon | 2.50 |
| 8 | Cable gland / strain relief | PG7 nylon gland OR rubber grommet + zip-tie anchor | 1 | any | 0.30 |
| 9 | Hookup wire / header | Dupont jumpers or 22 AWG solid, plus 0.1" header if socketing | small | any | 0.20 |
| 10 | Misc (solder, heatshrink, standoffs) | consumables, amortized per unit | — | — | 0.40 |

**Core per-unit material cost ≈ $17.49** (round to **~$17.50**).
Buying dev boards and probes in 10+ qty typically drops this to **~$13–14/unit**.

### Optional: MAX31855 K-type thermocouple build

Populate these *instead of* the DS18B20 (items 2 + 3 above) when you need
high-temperature or fast-response probes and build firmware with `-D SENSOR_MAX31855`.

| # | Component | Spec / part example | Qty | Example supplier | Unit cost (USD) |
|---|-----------|---------------------|-----|------------------|-----------------|
| A | MAX31855 breakout | K-type thermocouple-to-SPI amp, 3.3 V | 1 | Adafruit #269 | 14.95 |
| B | K-type thermocouple | Bead or probe type-K, glass/PTFE lead | 1 | Adafruit #270 / Amazon | 6.00 |

Adds **~$21** to the unit; **thermocouple per-unit material cost ≈ $36** (offset
by removing the DS18B20 + pull-up, −$3.52 → net **~$34.50**).

### Optional: SHT4x temperature + humidity build ("grow" variant)

Populate this *instead of* the DS18B20 (items 2 + 3 above) when you want humidity and
hub-computed **VPD** for grow tents / greenhouses, and build firmware with
`-D SENSOR_SHT4x`. The SHT4x is a digital I2C part, so it needs **no** 4.7 kΩ pull-up
(item 3) and no waterproof stainless probe (item 2).

| # | Component | Spec / part example | Qty | Example supplier | Unit cost (USD) |
|---|-----------|---------------------|-----|------------------|-----------------|
| S | SHT4x breakout | SHT40/SHT41/SHT45 temp + humidity, I2C (SDA/SCL), 3.3 V | 1 | Adafruit #4885 (SHT40) / Amazon | 4.95 |

Adds **~$5** for the module and removes the DS18B20 + pull-up (−$3.52), so the
**grow per-unit material cost ≈ $19** (net **~$18.90**). For a vented (non-immersed)
grow-tent enclosure the sensor must sit in free air — see ASSEMBLY.md.

---

## Suggested retail pricing

Pricing assumes small-maker assembly (hand-soldered, flashed, tested) and a
target gross margin around 55–60% to cover labor, test time, returns, packaging,
and the printed unit label/QR.

| Build | Material cost | Assembly + test (labor) | Suggested landed cost | **Suggested retail** | Gross margin |
|-------|---------------|--------------------------|-----------------------|----------------------|--------------|
| DS18B20 (standard) | ~$17.50 | ~$8 (≈20 min @ $24/hr) | ~$25.50 | **$59** | ~57% |
| MAX31855 (thermocouple) | ~$34.50 | ~$8 | ~$42.50 | **$99** | ~57% |

Notes on pricing:
- These are *single-unit maker* numbers. At batch scale (parts in 10s–100s,
  jigged flashing/test) landed cost drops materially and you can either widen
  margin or cut retail to ~$45 / ~$85.
- ThermaHub is the free local-first software; the ThermaProbe hardware is the
  revenue item. One hub can serve many probes, so upsell is additional probes.

---

## Waterproofing & food-safe notes

- The **stainless DS18B20 probe tip is the only part rated for immersion.** The
  ESP32, resistor, and LED live inside the enclosure and must stay dry.
- For fridge / freezer / fermentation: the stainless probe tip is food-contact
  safe for **incidental contact** (e.g. dangling in a fermentation vessel or
  clipped inside a fridge). For **submerged food-safe** use (in-liquid, extended),
  sheath the tip in food-grade silicone or a thermowell and keep the epoxy joint
  out of the product.
- Seal the cable entry with the gland/grommet (item 8) so condensation and wash-down
  don't wick into the box. Add a bead of neutral-cure (non-acetic) silicone around
  the gland for freezer/greenhouse humidity.
- Do **not** immerse the K-type MAX31855 bead thermocouples unless they are the
  sealed/probe variety — bare bead junctions are not waterproof.
- Provide **strain relief** on the probe lead (cable gland or an internal zip-tie
  anchor) so pulling the cable never stresses the solder joints. This is the #1
  field-failure cause.
- Keep the DS18B20 lead reasonably short (≤3 m) for reliable OneWire timing; the
  4.7 kΩ pull-up (item 3) is mandatory — the bus will not read without it.
