# Setpoint rev 3 — design notes

> **Status: proposal.** Rev 2 is built and bench-verified; nothing here is cut yet.
> Companion to [`REV2_SCHEMATIC.md`](REV2_SCHEMATIC.md), which stays the record of
> what exists today.

## Why now, and why not later

Rev 3 changes are **free before the Part 15B SDoC and expensive after it.**

SDoC has no permissive-change mechanism — that exists for *certified* equipment
under 47 CFR §2.1043, not for self-declared conformity. Under SDoC you are the
responsible party, so if you change the product you must be able to defend that
it still complies. Adding a DC-level trace and an LED is a defensible
non-significant change on paper, but that judgement is yours to hold, and in
practice most small makers re-test rather than argue it.

The SDoC has not been done. So the window is open **now** and closes the day the
test report is signed. Anything on this page that is worth doing at all is worth
doing before that, especially since the enclosure is not frozen either and two of
these items change what the case needs.

---

## 1. Charge-complete detection ⭐ the one that prompted this

**Today:** the TP4056 (`U5`) signals charge-complete on `STDBY` (pin 6) and rev 2
leaves that pin **explicitly no-connected**. `CHRG` (pin 7) drives `D2` through
`R12` to VBUS, which is the red charging light. The chip is announcing "done" and
nothing is listening — so there is no finished-charging indication, and the ESP32
cannot know the charge state either.

Both pins are **open-drain**: pulled low when active, high-Z otherwise. That means
one pull-up each and they can drive an LED, a GPIO, or both.

### 1a. Minimum fix — a second LED (parts only, no firmware)

Mirror the existing `CHRG` arrangement on `STDBY`:

```
VBUS ---[R13 1k]---|>|--- U5 pin 6 (STDBY)      D3, green or blue
```

Same topology as `D2`/`R12`. Red on = charging, green on = done. This is the
behaviour of every off-the-shelf TP4056 module and costs two parts.

### 1b. Better — let the firmware read both pins

Route both status pins to spare GPIOs with pull-ups to 3V3. Read together they
give a clean three-state, which an LED pair cannot express as compactly:

| `CHRG` | `STDBY` | State |
|---|---|---|
| low | high | Charging |
| high | low | **Charge complete** |
| high | high | No USB power (both outputs high-Z) |

Suggested pins — anything free; **do not** use IO2, IO8 or IO9 (strapping), and
keep ADC1 free for §2:

| Signal | Pin | Notes |
|---|---|---|
| `CHRG` → | `IO6` | 100 kΩ pull-up to 3V3 |
| `STDBY` → | `IO7` | 100 kΩ pull-up to 3V3 |

Firmware can then blink `D1` distinctly while charging, and report charge state to
the hub. Do 1a **and** 1b — the LED works with the board unpowered and off the
network, which is exactly when someone is standing there watching it charge.

---

## 2. Battery sense — turn on a feature that is already built ⭐⭐

**This is the highest-value item on the page, because the software half is done.**

The hub has a complete, dormant battery pipeline:

| Layer | State |
|---|---|
| `PROTOCOL.md` §7 | `battery_pct` and `battery_v` defined as optional fields |
| `core/storage.py` | Accepts either; maps 3.0 V → 0 %, 4.2 V → 100 %, rejects junk outside 2.5–5.0 V |
| `core/db.py` | `battery_pct` column exists |
| `api/routes.py` | Field exposed on readings |
| Dashboard + Devices | Render **Batt NN%**, amber under 20 % |

The firmware sends neither field, and no board revision has a circuit that could
measure one — rev 2 has eight nets and none is a VBAT divider. Two resistors turn
all of the above on.

### The trap that will cost you a day

**On ESP32-C3, ADC2 is unusable while Wi-Fi is active.** A divider wired to an
ADC2 pin reads correctly on the bench with the radio idle and returns garbage the
moment the probe associates — an intermittent failure that looks like a bad
solder joint.

- **ADC1 = IO0, IO1, IO2, IO3, IO4** ← use one of these
- ADC2 = IO5 — already the DS18B20 line anyway, and unusable with Wi-Fi

**Use `IO3` or `IO4`.** Avoid `IO2`: it is ADC1-capable but also a strapping pin,
and a divider sitting on it at ~2 V is an argument you do not need at boot.

### Circuit

```
VBAT ---[R14 470k]---+---[R15 470k]--- GND
                     |
                     +---[C6 100n]--- GND
                     |
                     +--- U1 IO3 (ADC1_CH3)
```

- **470 k / 470 k** divides by 2, so a 4.2 V cell reads 2.1 V at the pin — inside
  range with 11 dB attenuation, and safely under the 3V3 rail at all times.
- Continuous drain is `4.2 V / 940 kΩ ≈ 4.5 µA`, negligible against the deep-sleep
  budget (the board idles under 1 mA).
- `C6` gives the ADC a low-impedance source to sample; without it a ~235 kΩ
  Thévenin source and the C3's sampling capacitor produce readings that drift with
  sample rate.
- Report **`battery_v`** rather than `battery_pct` and let the hub do the mapping —
  it already does, it is the documented preference in `PROTOCOL.md` §7, and it
  means the curve can be improved later in hub software with no reflash.

**Calibrate:** the C3's ADC is not precise out of the box. Read the eFuse
calibration if present, and expect to trim with a per-board offset. A reading
that is confidently wrong is worse than none — it is the same argument as the
±0.5/±2 °C banding on the probe.

---

## 3. Worth considering while the board is open

Ordered by value, not effort. None is required.

- **Test points on VBAT, 3V3, GND.** Two pads and a via each. The next person to
  debug a dead unit — probably you, holding a probe in one hand — will get them
  back immediately.
- **A reverse-polarity / inrush part on VIN.** The 18650 holder makes it possible
  to insert a cell backwards. A series Schottky costs a diode drop; a P-FET costs
  more parts and almost nothing in voltage. Cheap insurance on a user-replaceable
  cell.
- **Thermal relief for `U5` at 1 A.** See §4 — this interacts with the enclosure.
- **Pull the `PROG` resistor to a footprint you can change.** `R11` sets charge
  current (§4). Keeping it 0805 and reachable means changing the charge rate is a
  rework, not a respin.
- **A second DS18B20 header.** 1-Wire is a bus; a second `J1` costs a connector
  and lets one probe watch a fridge *and* its freezer compartment. It is also the
  cheapest possible answer to "can I monitor two things?" on a sales call.
- **Silkscreen the FCC block.** Once the SDoC is signed the label must carry
  "Contains FCC ID: 2AC7Z-ESPC3MINI1", the §15.19(a)(3) statement and the
  responsible party ([`LABEL_TEMPLATE.md`](LABEL_TEMPLATE.md)). Some of that can be
  silkscreen instead of a sticker that can peel.

---

## 4. Charge current, heat, and the enclosure — decide together

`R11 = 1.2 kΩ` programs the TP4056 to **1000 mA**, its maximum:

> `I_BAT = (V_PROG / R_PROG) × 1200`, with `V_PROG ≈ 1.0 V` → `1200 / 1.2 kΩ = 1 A`

Charge time from empty, allowing for the constant-voltage taper (real time runs
about 1.3× naive capacity ÷ current; termination fires near 100 mA):

| Cell | @ 1000 mA (`R11` = 1.2 kΩ) | @ 580 mA (`R11` = 2 kΩ) |
|---|---|---|
| 2500 mAh | ~3–3.5 h | ~5–6 h |
| 3500 mAh | ~4.5–5 h | ~7–8 h |

**The catch is heat, and it lands on the enclosure.** Early in a charge the
TP4056 dissipates `(5 V − 3.0 V) × 1 A ≈ 2 W` in an ESOP-8. The part has thermal
regulation that folds current back as the die nears ~120 °C, so inside a sealed
printed case the current drops and those times stretch — and a warm component
sits next to a lithium cell.

Three ways to resolve it, in order of preference:

1. **Measure first.** Tape a thermocouple to `U5` and run a full charge in the
   candidate enclosure. You already own the instrument, and this converts a guess
   into a number.
2. **Drop to ~580 mA** (`R11` = 2 kΩ). Halves the heat, gentler on the cell, and
   an overnight charge does not care about 5 h vs 3 h.
3. **Keep 1 A** and pay for it in copper pour under the EPAD plus a vent path.

**Enclosure decisions this forces — make them before the case is frozen:**

- **How many LED windows?** `D1` (status, on the carrier) and `D2` (charge, on the
  TP4056) are in different places. Adding `D3` from §1a makes three. A case cut for
  one window hides the charge state completely once the board is inside.
- **Vent path over `U5`** if you keep 1 A.
- The SDoC covers the product **as it ships**, enclosure included — so the case and
  the board want to be settled in the same pass.

---

## Sequence

1. Decide charge current (§4) — it is a resistor value, but it drives the thermal
   design and therefore the case.
2. Cut §1 and §2 into the schematic; they are five passives and three pins.
3. Freeze the enclosure around the resulting LED count and thermal path.
4. Build, bench-verify, **then** book the SDoC on the finished product in its case.
5. Firmware: read `CHRG`/`STDBY`, sample `IO3`, add `battery_v` to the ingest
   payload. The hub needs no change — it has been ready the whole time.
