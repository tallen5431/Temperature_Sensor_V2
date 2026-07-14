# TempSensor — Rev 2 Board Spec (swap SuperMini → pre-certified module)

> **Why this exists:** the rev-1 board sockets an **ESP32-C3 SuperMini** (bare `ESP32-C3FH4` +
> PCB trace antenna), which carries **no modular FCC grant** — so assembled units can't take the
> cheap Part 15B SDoC path (see [`STARTUP_CHECKLIST.md`](STARTUP_CHECKLIST.md)). Rev 2 replaces it
> with a soldered-down, pre-certified **`ESP32-C3-MINI-1`** module (FCC ID `2AC7Z-ESPC3MINI1`).
> Same ESP32-C3 chip, **zero firmware change**.

## Honest scope — this is more than a footprint swap

The SuperMini was quietly doing a lot for you: 3.3 V regulation, USB, the EN reset network, the boot
button, and decoupling. When you move to a **bare module**, your carrier board has to provide those
itself. It's a well-trodden, ~10-part circuit (Espressif publishes the reference), and **JLCPCB can
place all of it** — but plan for it as a real (small) circuit board, not a passive carrier.

**Good news:** unlike the SuperMini, the `ESP32-C3-MINI-1` has an **official KiCad footprint**
(`RF_Module:ESP32-C3-MINI-1`) and symbol — no custom footprint to draw this time.

## 1. Module choice

| Option | Antenna | Use it when |
|---|---|---|
| **ESP32-C3-MINI-1** (FCC ID `2AC7Z-ESPC3MINI1`) | On-module PCB antenna | Default. Module sits at the board edge, antenna facing out. |
| **ESP32-C3-MINI-1U** | U.FL → external antenna | If the unit lives inside a **metal enclosure** or a walk-in wall where an internal antenna won't radiate. |

## 2. The support circuit you now provide (the ~10 parts)

| Block | Parts | Notes |
|---|---|---|
| **3.3 V regulator** | 1× LDO + 2 caps | From 5 V USB **or** TP4056 battery (~3.0–4.2 V). Use a **low-dropout** LDO (**RT9013-33** or **ME6211C33**, ~250 mV dropout, ≥500 mA) so it still holds 3.3 V on a low battery. `AMS1117-3.3` is fine **only** for a USB-always-on (5 V) build — its 1.1 V dropout browns out on battery. |
| **EN reset** | 10 kΩ pull-up (EN→3V3) + 1 µF (EN→GND) | Standard power-on reset delay. |
| **Boot / download** | button or test pad IO9→GND | Hold at power-up to enter flash mode. IO9 has an internal pull-up. |
| **IO8 strap** | 10 kΩ pull-up IO8→3V3 | IO8 is a **strapping pin** and must be high at boot. Your status LED is on IO8, so keep it pulled high (don't let the LED hold it low at reset). |
| **Decoupling** | 10 µF + 100 nF on module 3V3 | Place close to the module's 3V3 pin. |
| **Programming** | see §4 | UART header (simplest) or native USB-C. |

## 3. Pin / net mapping (by function — place per the KiCad footprint + module datasheet)

Your firmware is unchanged, so the GPIO assignments stay identical to rev 1:

| Your net (rev 1) | ESP32-C3-MINI-1 pin | Notes |
|---|---|---|
| DS18B20 **data** | **IO5** | Keep the **4.7 kΩ pull-up IO5→3V3** (mandatory for 1-Wire). |
| DS18B20 VDD / GND | 3V3 / GND | Probe powered from 3V3. |
| Status LED | **IO8** | Plus the 10 kΩ boot-strap pull-up above. |
| 3.3 V rail | 3V3 (+ center GND pad) | From your LDO; tie the module's big center pad to GND. |
| GND | GND (multiple) | Star/plane ground. |
| Battery / 5 V in | → LDO input | From TP4056 OUT (battery) or USB 5 V. |

> Reference exact castellation numbers on the **ESP32-C3-MINI-1 datasheet** / the KiCad symbol — the
> functions above are what matter; don't hard-code pin numbers from memory.

## 4. How you flash it — pick one

- **UART header (simplest, cheapest — recommended for the factory-flashed restaurant SKU).**
  Expose 6 pads: **3V3, GND, EN, IO9 (BOOT), IO20 (RX), IO21 (TX)**. Flash on the bench with a
  USB-UART adapter — this matches your existing `firmware/factory_flash.py` serial flow. No USB
  connector or ESD parts on the product.
- **Native USB-C (keeps browser-flashing).** ESP32-C3 has native USB on **IO18 (D−) / IO19 (D+)**;
  add a USB-C connector (+ 5.1 kΩ CC resistors + a USB ESD array). Costs a few parts but keeps your
  **ESP Web Tools browser-flash** page working — nice for the **DIY/homelab SKU**. Consider USB-C on
  the homelab board, UART-only on the sealed restaurant board.

## 5. Antenna keep-out (don't skip — it's part of keeping the FCC grant)

- Place the module at the **board edge**, antenna end pointing **off the board**.
- **No copper** under or beside the antenna: no ground pour, no traces, no parts in the module's
  published keep-out zone (a copper-free cutout region at the antenna end).
- Follow Espressif's **KDB 996369** integration guidance and keep the module **unmodified** with its
  approved antenna — that's the condition under which the modular grant transfers to your finished unit.

## 6. What JLCPCB places vs. what you hand-solder

- **JLC PCBA (from LCSC stock):** the **ESP32-C3-MINI-1 module**, the LDO, all the caps/resistors,
  and the USB-C connector + ESD if you use it. This solves the "module is surface-mount" problem —
  JLC places it correctly, antenna keep-out respected.
- **You hand-solder (or add as JLC THT):** the through-hole connectors — DS18B20 3-pin header, the
  TP4056 tie-ins, the slide switch, and the battery leads. Same easy parts you already solder today.

## 7. Suggested next step

Keep rev 1 for **pilots + DIY kits**. When you're ready to build the assembled, certifiable SKU,
open a fresh KiCad board: reuse the **70×30 outline and connector placements**, drop in
`RF_Module:ESP32-C3-MINI-1`, add the §2 support circuit, wire §3, honor §5, and export for a
**JLCPCB PCBA** order. Then the Part 15B SDoC + "Contains FCC ID: 2AC7Z-ESPC3MINI1" label
([`STARTUP_CHECKLIST.md`](STARTUP_CHECKLIST.md) Phase 2).
