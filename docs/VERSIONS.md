# Setpoint — Product Versions (one board, two use cases)

> **The single source of truth for the two Setpoint versions.** They are the *same* carrier board,
> the *same* DS18B20 probe, and the *same* firmware image — the only differences are the **power
> hardware** and the **read interval**. When any other doc (BOM, DIY kit, listing, pilot offer)
> describes power or battery behaviour, it should say **which version** and point here.

---

## The two versions

| | **Setpoint Portable** | **Setpoint Fixed** |
|---|---|---|
| **One-liner** | A battery tool you move to wherever you need a reading | A wired sensor you mount once and leave running |
| **Use it like** | A thermometer you carry — spot-check a fridge, a fermenter, a crawlspace, a car, a cold-chain hand-off | A permanent monitor — walk-in cooler/freezer, server rack, greenhouse, anywhere with power |
| **Power** | Protected 18650 / LiPo + TP4056 charge board + on/off switch | USB-C from any 5 V wall adapter or the hub PC — **no battery** |
| **Firmware behaviour** | Deep-sleeps between readings (idle **<1 mA**) → long runtime | Stays **always-on** → web page + mDNS continuously reachable, live readings |
| **How it's set** | Default firmware, read interval **≥ 10 s** | Same firmware, read interval **< 10 s** (or build with `DEEP_SLEEP_ENABLED=false`) |
| **Reachability** | Answers its local URL only for ~3 s at each wake — **tap reset to wake it** on demand | Answers continuously — good for live dashboards and instant alerts |
| **Trade-off** | Lithium handling + shipping rules; not continuously reachable | Needs a nearby power outlet; monitoring stops in a power outage (but so does the fridge) |
| **Best market** | Homelab / makers / anyone needing portability → **DIY kits** | Restaurants / fixed installs → **loaner pilots** and the future assembled unit |

> **Same firmware, convertible in the field.** Because the split is just power + interval, a Portable
> unit plugged into USB with a short interval *becomes* a Fixed unit, and vice-versa. You stock **one
> board and one firmware image** — the "version" is which power parts you bag and what interval it runs.

---

## What changes in the parts list

Everything in the **shared core** is identical (carrier board + ESP32-C3 + DS18B20 probe + the
mandatory 4.7 kΩ pull-up + enclosure/gland). Only the power block differs — see [`BOM.md`](BOM.md)
for costed lines.

- **Portable adds:** protected 18650 (or LiPo) · TP4056 USB-C charge/protect board · battery holder /
  JST pigtail · slide on/off switch. *(Ship kits **cell-not-included** — lithium carrier rules.)*
- **Fixed adds:** nothing — it **drops** the battery/TP4056/switch and runs from a **USB-C wall
  adapter**. Fewer parts, lower cost, no lithium liability. This is the right build for a restaurant
  walk-in (mains power is always there) and for the hardened pilot loaners in [`PILOT_OFFER.md`](PILOT_OFFER.md).

---

## How the versions map to how you sell

| Channel | Version | Why |
|---|---|---|
| **Tindie DIY kit** ([`DIY_KIT.md`](DIY_KIT.md), [`TINDIE_LISTING.md`](TINDIE_LISTING.md)) | **Portable** (default) — offer **Fixed** as a cheaper "no-battery / USB" option | Makers want the portable tool; some just want a cheap always-on rack/greenhouse probe |
| **Restaurant loaner pilots** ([`PILOT_OFFER.md`](PILOT_OFFER.md)) | **Fixed** | Walk-ins have power; a battery is pure liability (swaps, lithium). Always-on = live alerts |
| **Future assembled unit** ([`REV2_BUILD_GUIDE.md`](REV2_BUILD_GUIDE.md)) | **Fixed** first (USB-always-on, certify this SKU first), Portable variant later | Fewest parts / RF variables to take through the FCC SDoC |

---

## Firmware reference

Both versions run `esp32_temp_probe/esp32_temp_probe.ino` unchanged. The behaviour is controlled by two
knobs documented in `firmware/src/protocol.h`:

- `DEEP_SLEEP_ENABLED` (default `true`) — set `false` to force always-on regardless of interval.
- `DEEP_SLEEP_MIN_MS` (default `10000`) — deep sleep engages **only** when the configured read interval
  is at or above this. A Fixed unit simply runs a shorter interval, so it never sleeps and stays
  continuously reachable (WiFi modem-sleep only).

> **⚠ Board/firmware reconciliation still pending (tracked in
> [`MATERIALS_AND_NEXT_STEPS.md`](MATERIALS_AND_NEXT_STEPS.md) #1).** The pin map in `protocol.h` +
> `BOM.md` currently targets the **ESP32-WROOM-32** (status LED on GPIO2, active-high). The rev-1
> boards you're building on are **ESP32-C3 SuperMini** (onboard LED on GPIO8, active-**low**, and a
> boot strapping pin). This is independent of the Portable/Fixed split and must be fixed in firmware +
> BOM **before you flash the batch** — see that doc's item #1.
