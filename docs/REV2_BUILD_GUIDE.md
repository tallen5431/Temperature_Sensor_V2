# TempSensor — Rev 2 Build Guide (module-based, certifiable, assembly-ready)

> Build companion to [`PCB_REV2_MODULE.md`](PCB_REV2_MODULE.md) (the *why* + spec). This is the
> *how*: the concrete parts list, a step-by-step KiCad flow, and how to order it assembled from
> JLCPCB. **This is the board you can legally sell fully assembled** (after the Part 15B SDoC in
> [`STARTUP_CHECKLIST.md`](STARTUP_CHECKLIST.md)) — because it's built on a pre-certified module.

---

## 1. Rev-2 Bill of Materials (the parts that make assembled sales legal)

The **one part that unlocks assembled sales** is the pre-certified module (row 1). Everything else is
the small support circuit the SuperMini used to hide. Part numbers below are stable manufacturer
numbers — when you order, confirm current **LCSC stock + JLC "Basic vs Extended"** status (Basic
parts have no per-part loading fee, so prefer them where possible).

| Ref | Part | Value / MPN | Pkg | JLC note |
|---|---|---|---|---|
| **U1** | **ESP32-C3-MINI-1-N4** (FCC ID `2AC7Z-ESPC3MINI1`) | genuine Espressif, 4 MB | module | The enabling part. Use `-1U` for a U.FL external antenna. |
| U2 | **3.3 V LDO**, low-dropout ≥500 mA | ME6211C33M5G-N *or* RT9013-33GB | SOT-23-5 | ME6211 is JLC Basic. (AMS1117-3.3 only if USB/5 V-only — browns out on battery.) |
| C1 | LDO input cap | 10 µF | 0805 | |
| C2, C3 | 3V3 decoupling (at module) | 10 µF + 100 nF | 0603/0402 | Place at U1's 3V3 pin. |
| C4 | EN RC cap | 1 µF | 0402 | EN → GND. |
| R1 | EN pull-up | 10 kΩ | 0402 | EN → 3V3. |
| R2 | **IO8 boot-strap pull-up** | 10 kΩ | 0402 | IO8 must be high at boot (LED lives here). |
| R3 | DS18B20 1-Wire pull-up | 4.7 kΩ | 0402 | IO5 → 3V3. **Mandatory.** |
| R4 | LED series resistor | 330–1 kΩ | 0402 | For the IO8 status LED. |
| D1 | Status LED | any color | 0603 | IO8. |
| SW1 | BOOT button | tact switch | SMD | IO9 → GND (download mode). |
| SW2 | RST button (optional) | tact switch | SMD | EN → GND. |
| J1 | DS18B20 connector | 3-pin (JST-PH or header) | THT | Probe. |
| J2 | **Program/flash** | see §2 | — | UART header **or** USB-C. |
| — | Power path (reuse rev 1) | TP4056 charger + slide switch + 18650 holder | — | Same as your current board. |

### The two flashing options (pick per SKU)
- **UART header (J2 = 1×6): 3V3 · GND · EN · IO9 · IO20 (RX) · IO21 (TX).** Cheapest; matches your
  `firmware/factory_flash.py`. Operator holds BOOT, taps RST to enter flash mode. Best for the
  **sealed restaurant unit**. (Optional: add 2 auto-reset transistors so no buttons are needed.)
- **Native USB-C:** USB-C receptacle + 2× 5.1 kΩ CC pulldowns + a USB ESD array (e.g. USBLC6-2SC6),
  wired to **IO18 (D−) / IO19 (D+)**. Keeps your **ESP Web Tools browser-flash** page working — best
  for the **homelab/DIY SKU**.

---

## 2. Step-by-step KiCad flow (schematic-driven — the right way this time)

Rev 1 was freehand PCB-only. Rev 2 has real nets and a support circuit, so do it schematic-first —
KiCad then draws a **ratsnest** telling you exactly what connects to what, and ERC catches wiring
mistakes before you spend money.

1. **New project** in KiCad → open the **Schematic Editor**.
2. **Place symbols** (press `A`): `RF_Module:ESP32-C3-MINI-1`, the LDO (`Regulator_Linear`), caps,
   resistors, LED, the DS18B20 connector (`Connector`), the two tact switches, and your program
   header/USB-C.
3. **Wire it** per this connection list:
   - LDO in ← battery/5 V (from TP4056 OUT / USB); LDO out → **3V3** net; add C1 in, C2+C3 out.
   - **EN**: R1 (10 kΩ) to 3V3, C4 (1 µF) to GND, SW2 to GND.
   - **IO9** → SW1 (BOOT) to GND.
   - **IO8**: R2 (10 kΩ) pull-up to 3V3 (boot-strap), and the LED wired **active-low** —
     `3V3 → R4 → LED → IO8` (never `IO8 → LED → GND`; see the strapping-pin gotcha in
     [`REV2_SCHEMATIC.md`](REV2_SCHEMATIC.md) Net 6).
   - **IO5** → R3 (4.7 kΩ) to 3V3, and → J1 pin 2 (DS18B20 data). J1 pin 1 = 3V3, pin 3 = GND.
   - Program header/USB-C per §1.
   - Tie the module's **GND pins + center pad** to GND; **3V3 pin** to the 3V3 net.
4. **Assign footprints** (Tools → Assign Footprints): `RF_Module:ESP32-C3-MINI-1` for U1, `SOT-23-5`
   for the LDO, `0402/0603` for passives, your existing DS18B20/switch footprints.
5. **Run ERC** (Inspect → Electrical Rules Check); fix any unconnected-pin errors.
6. **Push to PCB**: open PCB Editor → **Update PCB from Schematic** (`F8`). Your parts drop in joined
   by a ratsnest.
7. **Place**: reuse your **70×30 Edge.Cuts outline** and the same DS18B20/TP4056/switch positions.
   Put **U1 at the board edge, antenna pointing off the board.**
8. **Antenna keep-out**: on the antenna end, add a **copper keep-out** (no pour, no traces, no parts)
   matching the module datasheet's keep-out zone. This is required to keep the FCC grant.
9. **Route** (`X`), following the ratsnest. Keep 3V3 decoupling caps right at the module.
10. **DRC** (Inspect → Design Rules Check); clear violations.
11. **Export for assembly**: Plot **Gerbers**, generate **drill files**, then File → Fabrication
    Outputs → **BOM** and **Component Placement (CPL/centroid)**.

---

## 3. Order it assembled from JLCPCB (PCBA)

1. Start a **PCB order**, upload Gerbers (as in rev 1), then turn on **PCB Assembly**.
2. Upload the **BOM** and **CPL** files.
3. JLC matches parts to LCSC stock — set which references JLC places: **U1 module, LDO, all caps,
   resistors, LED, tact switches, USB-C + ESD** (all SMD). Confirm each is in stock; swap any
   out-of-stock part for an equivalent.
4. Leave the **through-hole connectors** (DS18B20 J1, TP4056 tie-ins, slide switch, battery leads)
   for **hand-soldering** — same easy parts you do today. (Or pay for JLC THT assembly.)
5. Order a small assembled batch (5–10) first, **flash + QC** with `firmware/factory_flash.py` and
   `docs/QC_CHECKLIST.md`, verify the radio still associates and reads a probe, **then** scale.

---

## 4. What's certifiable vs. not — the bottom line

| Board | Radio | Sell assembled? | Sell as DIY kit? |
|---|---|---|---|
| **Rev 1** (SuperMini socket) | bare `ESP32-C3FH4` + PCB antenna, **no grant** | ❌ not without ~$5–15k full test | ✅ yes (buyer assembles) |
| **Rev 2** (`ESP32-C3-MINI-1`) | pre-certified module, grant transfers | ✅ yes, after ~$300–1,500 Part 15B SDoC | ✅ yes |

**Do the rev-2 respin only when pilots prove people will pay** — until then, rev-1 kits + pilots cost
you nothing and teach you the same lessons.
