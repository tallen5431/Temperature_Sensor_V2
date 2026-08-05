# Setpoint — Product Versions (one board, three configurations)

> **The single source of truth for the Setpoint configurations.** They are the *same* carrier board,
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
| **Trade-off** | Lithium handling + shipping rules; not continuously reachable | Needs a nearby power outlet. With no cell fitted, monitoring stops in a power outage — see *Fixed + backup cell* below, which is the same board with a small cell added |
| **Best market** | Homelab / makers / anyone needing portability → **DIY kits** | Restaurants / fixed installs → **loaner pilots** and the future assembled unit |

> **Same firmware, convertible in the field.** Because the split is just power + interval, a Portable
> unit plugged into USB with a short interval *becomes* a Fixed unit, and vice-versa. You stock **one
> board and one firmware image** — the "version" is which power parts you bag and what interval it runs.

---

## Fixed + backup cell (the third configuration)

**Rev 2 runs plugged in today**, so a Fixed unit is real hardware now, not a future SKU. Adding a
**small** cell — not the 18650 a Portable needs — turns the outage trade-off above into a feature:
mains runs the probe, and if the power drops the probe keeps reading and writes to its own flash
instead of going dark.

It works because of how the power block is already wired. `BOM.md` item 7 is a **TP4056 with battery
protection**, and `ASSEMBLY.md` takes the board's 5 V / GND / 3V3 **from the TP4056 output**, so the
load always sits on the cell while USB charges it. Losing USB is therefore seamless in *hardware* —
no firmware involvement, no changeover, nothing to detect. That is why a small cell buys real
resilience for very little money.

**What it does and does not promise.** Be precise about this in front of a food-safety customer:

| | During a power cut |
|---|---|
| **Keeps reading and storing** | **Yes**, but the buffer is finite and a Fixed unit fills it fast. `BUFFER_MAX_BYTES` = 1.9 MB at 56 bytes a reading = **34,742 readings**. A Fixed unit runs an interval *below* `DEEP_SLEEP_MIN_MS` (10 s) by definition, so at 5 s that is **2 days**, at 10 s **4 days**. Only at Portable-style intervals does it stretch — 24 days at 1 min, 121 days at 5 min. Once full, the oldest readings are what you lose. |
| **Keeps alerting** | **No.** The hub PC and the Wi-Fi access point are on the same failed mains. The probe cannot reach anything, so nobody is notified until power returns. |
| **Backfills afterwards** | **Yes.** On reconnect it drains the buffer through `/api/ingest_csv`, so the outage appears in the history with its real timestamps rather than as a hole. |

So the honest claim is **"you will not lose the record of what happened"**, never *"you will be
alerted during an outage."* The second is what a customer will hear if you let them, and it is not
true for any mains-powered monitor whose network is also on mains.

**How long the cell lasts is currently a firmware question, not a battery-size one.** A Fixed unit is
always-on by definition (interval < `DEEP_SLEEP_MIN_MS`), and the Wi-Fi backoff that conserves power
when the network is unreachable — `WIFI_FAIL_BACKOFF_AFTER` / `WIFI_FAIL_BACKOFF_EVERY` — is only
consulted on the **deep-sleep wake path** (`esp32_temp_probe.ino`, the `skipConnect` computation).
An always-on unit instead calls `WiFi.begin()` and blocks retrying, radio powered, for as long as the
outage lasts. That is the opposite of what you want on a backup cell.

> **Open item before this is sold as a feature.** Give the always-on path the same backoff: once the
> network has been unreachable for N attempts, power the radio down and keep reading to the buffer,
> retrying occasionally. That change earns twice — it is what makes a small cell last, *and* dropping
> to a longer interval while offline is what turns a 2-day buffer into a useful one. Until it lands,
> size the cell against a *continuously associating* radio (roughly 80–120 mA), not against the
> deep-sleep figures quoted for the Portable version, and do not quote an outage-endurance number.

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

> **Board:** both versions run on the **ESP32-C3 SuperMini** (rev-1). The firmware auto-targets it —
> status LED on **GPIO8, active-low**, kept boot-safe (GPIO8 is a strapping pin held high at reset) —
> and falls back to a WROOM's GPIO2 active-high when built for that board. Build/flash with FQBN
> `esp32:esp32:esp32c3`.
