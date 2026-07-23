# Assembly-guide images — commit checklist

[ASSEMBLY.md](../../ASSEMBLY.md) references the photos below. Save each of your build
shots into **this folder** (`docs/images/assembly/`) under the exact filename in the
first column, then commit — the guide will render. Until they're committed, the
`![](...)` links show as broken; that's expected.

**Before you save, for the phone screenshots:** crop tight to just the relevant
dialog/box. A few of your shots include personal content that shouldn't ship in a
public guide — the home screen with **Discord/Robinhood**, and your **real nearby
Wi-Fi names** (Eduardo2020, ATTDmWxaea, …). Crop those out.

General: landscape where possible, and compress to ~1600 px wide / a few hundred KB
so the page stays light.

| Save as | Step | What it shows | Which of your shots / crop notes |
|---|---|---|---|
| `01-esp32c3-solder.jpg` | 1 | ESP32-C3 soldered to the carrier | Your clean top-down of the mounted ESP, **or** the underside showing the joints. Pick the sharpest. |
| `02-tp4056-solder.jpg` | 2 | TP4056 soldered, kept level | The "tweezers under the board" shot. |
| `03-switch-resistor-probe.jpg` | 3 | Switch + 4.7 kΩ + probe fitted | The board held with the probe plugged into the JST. |
| `03b-jst-notch.jpg` | 3 | **JST notch faces the board edge** | **Tight crop** of the connector from the same shot — this is the key "don't reverse it" detail. |
| `04-battery-wires.jpg` | 4 | Holder wires passed through the back | The close-up of the red/black leads through the board near B+/B−. |
| `06-flash-port-picker.jpg` | 6 | Browser serial-port picker | The dialog with **"USB JTAG/serial debug unit (COM6)"** highlighted. Crop to the dialog. |
| `07-flash-complete.jpg` | 6 | "Installation complete!" | The 🎉 dialog (or the installing/progress shot). Crop to the card. |
| `08-finished-unit.jpg` | 7 | Finished unit: probe + board + 18650 | The flat-lay with the coiled probe, board, and battery in the holder. **This one doubles as a listing hero.** |
| `09-wifimanager.jpg` | 8 | WiFiManager page at `192.168.4.1` | The "WiFiManager / Setpoint-0000CA / Configure WiFi" screen. Crop to the page. |
| `10-blue-led-tx.jpg` | 9 | Blue LED flashing on upload | The powered-board shot with the blue LED lit. |
| `11-dashboard.jpg` | 9 | Live data on the dashboard | The Temperature History chart ("Last sync 1 s ago ✓"). |

## Optional extras (nice to have, not referenced yet)
- A **kit-contents flat-lay** (all parts laid out) — great for the listing and a "what's in the box" opener.
- The **red-LED "powered on"** close-up — an alternate for Step 7.
- The **"connected without internet → Connect"** phone prompt — an alternate for Step 8 (crop out the home-screen apps).

Once these are committed, tell me and I'll do a pass to confirm every image resolves
and tighten any caption to match what the final crop actually shows.
