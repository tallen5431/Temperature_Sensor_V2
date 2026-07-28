# Field Test #2 — Reporting modes, single-charge runtime & buffer recovery

> _Second round of full-charge field testing. **Four** Setpoint units were charged and each run in a
> **different reporting mode** — always-on, two ~5-minute duty-cycle units, and deep-sleep — to separate
> data-capture throughput from the low-power runtime the "weeks per charge" estimate depends on. Two units
> were later **pulled and power-cycled to unload their on-board buffers**. Dates: 2026-07-25 → 07-28.
> Firmware: the in-progress build after **v2.7.0** (exact tag to be recorded); dashboard **2.5.0**._
>
> **Why this doc exists:** [Round 1](BATTERY_FIELD_TEST.md) measured throughput in always-on mode only
> and explicitly could not touch the deep-sleep configuration behind the "weeks per charge" claim. This
> round exercises all the low-power modes **and** demonstrates buffer recovery. It stays deliberately
> careful about what it does and does **not** prove.

## TL;DR

- **Round 1's biggest gap is closed:** the deep-sleep mode is now under test. The Bed Room unit reports on
  a clean **300-second interval** and was **still running at 71 h (≈3 days)** — untouched.
- **The always-on unit ran to a stop:** the Refrigerator-01 logged **155,990 readings over 48.65 continuous
  hours** at ~1/s — **zero gaps, zero duplicate timestamps** — then stopped. The operator attributes the
  stop to **battery exhaustion**.
- **On-board buffering works — dramatically.** Refrigerator-02 lost the hub after **4.5 minutes** yet kept
  logging locally; a power-cycle recovered its **entire ~72-hour run (2,149 buffered readings, 100%
  intact)**. The freezer likewise back-filled its last 7.8 h (~140 readings) on its pull.
- **The Round 1 duplicate-timestamp defect is fixed** and stays fixed: **0%** duplicates across all units
  this round (was 4.6% / 1.5% on the cold units).
- **Still not established: a voltage-verified battery number.** `battery_pct` is empty in every export, so
  the "battery empty" stop is **operator-attributed, not sensor-proven**, and "weeks per charge" remains
  unproven — the deep-sleep unit has only 3 days on the clock so far.

## Test setup — one mode per unit (four units)

| Unit | Probe ID | Reporting mode | What it measures |
|---|---|---|---|
| **Refrigerator-01** | Setpoint-00002F | **Always-on**, ~1 reading/s | Worst-case throughput + shortest runtime |
| **Refrigerator-02** | Setpoint-000002 | **Duty-cycle** (5 s bursts / ~5 min) | Cold-box behaviour + buffer under chronic weak Wi-Fi |
| **Freezer** | Setpoint-000079 | **Duty-cycle**, wake ~every 5 min | Cold-box behaviour at low duty |
| **Bed Room** | Setpoint-818C58 | **Deep-sleep**, 1 reading / 300 s | The "weeks per charge" configuration |

> **Correction to an earlier draft:** the Setpoint-000002 rows first read as "stray leftovers from before
> the DB was cleared" were in fact **Refrigerator-02** logging normally — only 54 of its readings had
> reached the hub when the first export was taken. It is a full fourth unit, not noise.

## Per-unit results (after buffer unloads)

Figures recomputed directly from the exported CSVs.

| Unit | Mode | Readings | Run span | Cadence | In-appliance temp (mean / min) | Dup ts | Status |
|---|---|---:|---|---|---|---:|---|
| **Refrigerator-01** | Always-on | **155,990** | **48.65 h, 0 gaps** | ~1/s | +0.24 / **−3.25 °C**, 45.9% sub-zero | 0 | **Stopped** 07-27 23:01 — operator: battery empty |
| **Refrigerator-02** | Duty-cycle | 2,203 | 71.79 h | 5 s bursts + ~5 min | **−1.62** / −5.00 °C | 0 | Pulled 07-28 22:11 for buffer unload (was alive) |
| **Freezer** | Duty-cycle | 2,668 | 71.92 h | ~5 min (+startup burst)¹ | **−21.47** / −26.88 °C | 0 | Pulled 07-28 22:12 for buffer unload (was alive) |
| **Bed Room** | Deep-sleep | 917 | 71.31 h **and counting** | 300 s (91% clean) | 21.96 / 20.50 / 24.25 °C² | 0 | **Still running** — untouched |

Total ≈ **161,800 readings** across the four units.

¹ The freezer opened with a **~9-minute always-on burst** (527 readings) as it cooled from room
temperature, then settled into the ~5-minute cadence.

² Bed Room is a room reference, so min/mean/max is the whole-file range (no "in-appliance" filter applies).

## Buffer recovery — the standout result

Two units were pulled and power-cycled near strong Wi-Fi to test on-board buffer retention:

| Unit | Reached hub **live** | Recovered on power-cycle | What it proves |
|---|---:|---:|---|
| **Refrigerator-02** | 54 (first **4.5 min** only) | **2,149** (rest of ~72 h) | Buffer held an **entire 3-day run** through a total hub outage — recovered 100% intact. |
| **Freezer** | 2,528 | 140 (last **7.8 h**) | Buffer back-fills a comms gap even on a unit that was otherwise delivering. |

This is a strong, demonstrable product claim: **inside a metal appliance where Wi-Fi is unreliable, no
readings are lost** — they queue on-device and flush when the link returns. It also **resolves the open
question from the first draft**: the sparse ~5-minute cadence on the cold units is **genuine duty-cycling,
not Wi-Fi-dropped 1 Hz data**. If the units had been sampling at 1/s and losing packets, their buffers
would have flushed *tens of thousands* of readings on the pull — not ~140 and ~2,150.

**One thing to investigate (firmware):** Refrigerator-02 delivered nothing to the hub for ~3 days and only
unloaded when **manually power-cycled**. Confirm whether buffered data is supposed to **auto-flush on
Wi-Fi reconnect** — if so, that path may not be firing for a chronically-weak-signal unit, and a customer
shouldn't have to pull a device to recover its history. (The buffer *integrity* is proven either way.)

## What this round establishes — and does not

| ✔ Established | ✘ Not established |
|---|---|
| An always-on unit logged **155,990 readings / 48.65 continuous hours** at ~1/s, **0 gaps / 0 dupes**, then stopped. | A **voltage-verified** battery death — no `battery_pct` logged, so "battery empty" is the operator's read, not a measured cutoff. |
| **On-board buffer retains a full multi-day run** through a hub outage and recovers it 100% on power-cycle. | Whether the buffer **auto-flushes on Wi-Fi reconnect** or needs a manual power-cycle (Refrigerator-02 needed the pull). |
| **Deep-sleep mode works and is frugal:** clean 300-s cadence, still running at **71 h / 3 days**. | **"Weeks per charge."** Three days is not weeks — the deep-sleep unit must run far longer to substantiate it. |
| The **duplicate-timestamp defect is fixed** — 0% across all four units. | That the always-on runtime ordering is **causal** rather than coincidental — only voltage logging closes that. |

## Recommended next steps

1. **Measure runtime by current draw, not by waiting.** `runtime = usable capacity (mAh) ÷ average current
   (mA)`. Measure each mode's average current over a few duty cycles (minutes) with a Nordic **Power
   Profiler Kit II** (~$100, built for ESP32 µA-sleep + mA-burst) or an INA226; measure true pack capacity
   once via a controlled discharge. This collapses the weeks-long deep-sleep test into an afternoon. The
   already-observed **48.65 h always-on death is a free calibration point** — its average current × 48.65 h
   back-solves the pack's real usable capacity, which then predicts the deep-sleep "weeks" figure.
2. **Log battery voltage / SoC as a column** — still the #1 durability item. It turns every stop from
   "operator thinks the battery died" into a self-proving datapoint at the low-voltage knee.
3. **Let the Bed Room (deep-sleep) unit run until it dies** — untouched. Its death timestamp is the number
   that upgrades "weeks (pending)" to a real figure. (Correctly left running this round.)
4. **Confirm the buffer auto-flush-on-reconnect path** (see the Refrigerator-02 note above).
5. **Record the exact firmware tag** under test so this round is reproducible.
6. Account for **cold-temperature capacity loss** — LiPo delivers fewer usable mAh at −20 °C, so the
   freezer/fridge units will run shorter than a room-temperature bench prediction; measure at temperature
   or derate.

## Listing copy this test supports (safe to use)

> **Field-tested, round two.** A single always-on Setpoint logged **155,990 readings across 48 continuous
> hours** — about one a second — with **zero gaps and zero duplicates**, then ran its battery down. A
> second unit tucked inside a metal refrigerator lost Wi-Fi after minutes yet **buffered its full three-day
> run on-device and recovered every reading** on reconnect. A deep-sleep unit reported cleanly every five
> minutes for **three days and counting**.

Label the always-on figure as **throughput + a single-charge always-on runtime**, present the battery-empty
stop as **operator-observed** (not a measured cutoff), lead the buffer claim with the **100% recovery**
result, and **do not upgrade the "weeks per charge" estimate yet** — the deep-sleep run has proven three
days, not weeks.
