# Setpoint — Rev 2 Schematic (net-by-net, wireable in KiCad)

> The full connection list for the `ESP32-C3-MINI-1` board. Wire the KiCad symbols by **pin name**
> (the `RF_Module:ESP32-C3-MINI-1` symbol labels pins by function — you connect to `IO5`, `EN`, `3V3`,
> etc., not by castellation number). Reference designators match
> [`REV2_BUILD_GUIDE.md`](REV2_BUILD_GUIDE.md) §1. Confirm LDO/ESD pin numbers on their datasheets.

## Block overview

```
 [18650]--[TP4056]--OUT+--/ SW_PWR /--VIN--+--[U2 LDO]--3V3 rail
                                           |            |
 USB-C VBUS --------------------(charge)---+       [C2 10u][C3 100n]  (at module)
                                                        |
                                          +-------------+--------------------------+
                                          |             |            |             |
                                     U1 3V3 pin    R1 10k->EN   R2 10k->IO8   R3 4.7k->IO5
                                                        |            |             |
                                     [ESP32-C3-MINI-1]  EN net    LED(active-low) DS18B20 data
```

## Net 1 — VIN (raw supply, ~3.0–4.2 V battery or 5 V USB)

| From | To |
|---|---|
| TP4056 `OUT+` | `SW_PWR` pin 1 (slide switch = on/off) |
| `SW_PWR` pin 2 | **VIN** |
| VIN | U2 (LDO) `IN` |
| VIN | U2 `EN`/`CE` (tie to VIN = always on) |
| VIN | C1 (10 µF) → GND |

> **Two power builds — decide per SKU:**
> - **Restaurant / assembled unit → USB-always-on. Drop the battery entirely.** Feed VIN from USB
>   `VBUS` (5 V); omit the 18650/TP4056/switch. Walk-ins have power, so a battery is only a liability
>   (swaps, lithium shipping/safety). Simpler board, fewer parts, no cell to ship.
> - **Portable / homelab → battery**, exactly as rev 1.
> - ⚠️ A basic TP4056 module has **no true load-sharing** — its OUT just follows the cell, so don't
>   try to run the board "from USB through the TP4056." Either power from `VBUS` (USB build) **or**
>   from the battery (battery build); use USB-C only for charging + data on the battery build.

## Net 2 — 3V3 (regulated)

| From | To |
|---|---|
| U2 `OUT` | **3V3** |
| 3V3 | C2 (10 µF) → GND · C3 (100 nF) → GND **(place C3 at U1's 3V3 pin)** |
| 3V3 | U1 `3V3` |
| 3V3 | R1 (10 kΩ) → `EN` |
| 3V3 | R2 (10 kΩ) → `IO8` |
| 3V3 | R3 (4.7 kΩ) → `IO5` |
| 3V3 | R4 (330 Ω–1 kΩ) → D1 anode *(LED, see Net 6)* |
| 3V3 | J1 pin 1 (DS18B20 VDD) |

## Net 3 — GND

Tie together: U1 all `GND` pins **+ the module's center thermal pad**, U2 `GND`, every cap's ground
leg, TP4056 `OUT−`/`GND`, battery `−`, J1 pin 3, the button grounds, and (if used) USB-C `GND` + ESD
ground. Use a ground pour on the bottom/free areas — **but keep it out of the antenna keep-out.**

## Net 4 — EN (chip reset)

| From | To |
|---|---|
| U1 `EN` | R1 (10 kΩ) → 3V3 |
| U1 `EN` | C4 (1 µF) → GND |
| U1 `EN` | SW2 (RST button) → GND *(optional but handy)* |

## Net 5 — IO9 (BOOT / download-mode strap)

| From | To |
|---|---|
| U1 `IO9` | SW1 (BOOT button) → GND |

Hold BOOT while tapping RST to enter flash mode. IO9 has an internal pull-up (normal boot = high).

## Net 6 — IO8 status LED ⚠️ WIRE IT ACTIVE-LOW

**IO8 is a strapping pin — it must be HIGH at boot.** Wire the LED so it can't drag IO8 down at reset:

```
   3V3 ---[R4 330-1k]---|>|--- IO8        (D1: anode to R4, cathode to IO8)
   3V3 ---[R2 10k]------------ IO8        (boot-strap pull-up)
```

| From | To |
|---|---|
| U1 `IO8` | R2 (10 kΩ) → 3V3 (guarantees boot-high) |
| 3V3 | R4 → D1 anode; D1 cathode → U1 `IO8` |

Firmware drives IO8 **low** to light the LED. **Do NOT** wire it `IO8 → R → LED → GND` (active-high):
at boot that forms a divider that pulls IO8 below the logic-high threshold and the module may fail to
boot. (This is the classic ESP32-C3 GPIO8 gotcha.)

## Net 7 — DS18B20 sensor (J1, 3-pin)

| J1 pin | Net |
|---|---|
| 1 | 3V3 |
| 2 | `IO5` (DATA) — with R3 (4.7 kΩ) pull-up to 3V3 (**mandatory** for 1-Wire) |
| 3 | GND |

> **Harden the probe line (recommended for restaurant/long runs).** The DS18B20 lead runs 1 m+ into a
> cold, damp, static-prone walk-in — the #1 field failure. Add an **optional ~100 Ω series resistor**
> in the DQ line (between J1 pin 2 and IO5, pull-up still to 3V3 on the IO5 side) and a small **TVS/ESD
> diode** from DQ to GND at the connector. Keep the probe lead ≤3 m for reliable 1-Wire timing, and
> give it strain relief at the enclosure.

## Net 8 — Programming (pick ONE per SKU)

### Option A — UART header J2 (1×6) · simplest, factory-flash, matches `factory_flash.py`
| J2 pin | Net | Adapter side |
|---|---|---|
| 1 | 3V3 | (power sense / optional) |
| 2 | GND | GND |
| 3 | `EN` | (optional auto-reset) |
| 4 | `IO9` | (optional auto-reset) |
| 5 | `IO20` (U0RXD) | adapter **TX** |
| 6 | `IO21` (U0TXD) | adapter **RX** |

Buttons handle boot manually, so the header can be just TX/RX/3V3/GND (+ EN/IO9 if you add the two
auto-reset transistors later).

### Option B — Native USB-C J3 · keeps browser-flashing (homelab SKU)
| USB-C | To |
|---|---|
| `VBUS` | TP4056 `IN+` (charge) — and/or VIN for a USB-only build |
| `GND` | GND |
| `CC1` | R5 (5.1 kΩ) → GND |
| `CC2` | R6 (5.1 kΩ) → GND |
| `D+` (A6+B6 tied) | ESD array → U1 `IO19` |
| `D−` (A7+B7 tied) | ESD array → U1 `IO18` |
| ESD `U4` (USBLC6-2SC6) | on D+, D−, VBUS |

ESP32-C3 native USB-Serial-JTAG is on IO18 (D−)/IO19 (D+) — no series resistors needed.

## Unused strapping pin

- **IO2** — leave **unconnected**. It's a strapping pin that boots high on the chip's internal
  pull-up; if you ever see flaky boots, add a 10 kΩ pull-up to 3V3. Don't tie it low, and don't use it
  for the LED (that's IO8).

## Pre-flight checklist before you export Gerbers

- [ ] Module `3V3` decoupled with C2/C3; C3 physically at the module pin.
- [ ] EN: 10 kΩ pull-up + 1 µF present.
- [ ] IO8 LED is **active-low** + has its 10 kΩ pull-up.
- [ ] IO5 has the 4.7 kΩ pull-up.
- [ ] Module thermal pad tied to GND.
- [ ] Module at board edge; **antenna keep-out has no copper**.
- [ ] LDO caps are **ceramic X5R/X7R** (needed for LDO loop stability).
- [ ] **Test points** exposed for bring-up/QC: 3V3, GND, IO5, EN.
- [ ] ERC clean, then DRC clean.
