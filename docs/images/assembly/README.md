# Assembly-guide images — commit checklist

[ASSEMBLY.md](../../ASSEMBLY.md) references the photos below. Save each build shot
into **this folder** (`docs/images/assembly/`) under the exact filename in the first
column, then commit — the guide renders. Until a file is committed, its `![](...)`
link shows broken.

**Before you save the phone screenshots:** crop tight to just the relevant dialog.
A few shots include personal content that shouldn't ship publicly — the home screen
with **Discord/Robinhood**, and your **real nearby Wi-Fi names**. Crop those out.
General: landscape where possible, compressed to ~1600 px wide.

## Steps 1–4 — trace-side build (✅ committed)

| File | Step | Shows |
|---|---|---|
| `01-esp32c3-solder.jpg` | 1 | ESP32-C3 header pins soldered (trace side) ✅ |
| `02-switch-resistor-probe.jpg` | 2 | Switch + 4.7 kΩ + DS18B20 connector soldered — trace side complete ✅ |
| `03-tp4056-solder.jpg` | 3 | TP4056 mounted and soldered on top ✅ |
| `04-battery-wires.jpg` | 4 | 18650 holder wires passed through the back ✅ |

> Step 5 ("Verify before you power it" — the multimeter checks) is intentionally
> **text-only**; there's nothing to photograph, so it needs no image.

## Steps 6–9 — flash, power, Wi-Fi, dashboard (⏳ still to commit)

| Save as | Step | What it shows | Which of your shots / crop notes |
|---|---|---|---|
| `06-flash-port-picker.jpg` | 6 | Browser serial-port picker | The dialog with **"USB JTAG/serial debug unit (COM6)"** highlighted. Crop to the dialog. |
| `07-flash-complete.jpg` | 6 | "Installation complete!" | The 🎉 dialog (or the installing/progress shot). Crop to the card. |
| `08-finished-unit.jpg` | 7 | Finished unit: probe + board + 18650 | The flat-lay with the coiled probe, board, and battery in the holder. **Doubles as a listing hero.** |
| `09-wifimanager.jpg` | 8 | WiFiManager page at `192.168.4.1` | The "WiFiManager / Setpoint-0000CA / Configure WiFi" screen. Crop to the page. |
| `10-blue-led-tx.jpg` | 9 | Blue LED flashing on upload | The powered-board shot with the blue LED lit. |
| `11-dashboard.jpg` | 9 | Live data on the dashboard | The Temperature History chart ("Last sync 1 s ago ✓"). |

## Optional extras (nice to have)
- A **kit-contents flat-lay** — great for the listing and a "what's in the box" opener.
- The **red-LED "powered on"** close-up — an alternate for Step 7.

Once the rest are committed, tell me and I'll do a pass to confirm every image
resolves and tighten any caption to match the final crop.
