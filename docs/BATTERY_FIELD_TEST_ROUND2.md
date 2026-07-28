# Field Test #2 — Reporting modes & single-charge runtime

> _Second round of full-charge field testing. Three Setpoint units were charged and each run in a
> **different reporting mode** — always-on, ~5-minute duty-cycle, and deep-sleep — to separate
> data-capture throughput from the low-power runtime the "weeks per charge" estimate depends on.
> Dates: 2026-07-25 → 07-28. Firmware: the in-progress build after **v2.7.0** (exact tag to be
> recorded); dashboard **2.5.0**._
>
> **Why this doc exists:** [Round 1](BATTERY_FIELD_TEST.md) measured throughput in always-on mode only
> and explicitly could not touch the deep-sleep configuration behind the "weeks per charge" claim. This
> round exercises all three modes. It is, again, deliberately careful about what it does and does **not**
> prove — and this time one unit was run until the operator observed it stop.

## TL;DR

- **Round 1's biggest gap is closed:** the deep-sleep mode is now under test. The Bed Room unit reports
  on a clean **300-second interval** and was **still alive at 71 h (≈3 days)** when this export was taken.
- **The always-on unit ran to a stop:** the Refrigerator logged **155,990 readings over 48.65 continuous
  hours** at ~1/s — **zero gaps, zero duplicate timestamps** — then stopped. The operator attributes the
  stop to **battery exhaustion** (~150k-reading full-charge run).
- **The Round 1 duplicate-timestamp defect is fixed.** The refrigerator went from **4.6% → 0%** duplicate
  rows; the freezer from **1.5% → 0%**. Clean data across the board.
- **Still not established: a voltage-verified battery number.** `battery_pct` is empty in every export,
  so the "battery empty" stop is **operator-attributed, not sensor-proven**, and "weeks per charge"
  remains unproven — the deep-sleep unit has only 3 days on the clock so far.

## Test setup — one mode per unit

| Unit | Probe ID | Reporting mode | What it measures |
|---|---|---|---|
| **Refrigerator-01** | Setpoint-00002F | **Always-on**, ~1 reading/s | Worst-case throughput + shortest runtime |
| **Freezer** | Setpoint-000079 | **Duty-cycle**, wake ~every 5 min | Cold-box behaviour at low duty |
| **Bed Room** | Setpoint-818C58 | **Deep-sleep**, 1 reading / 300 s | The "weeks per charge" configuration |

(A handful — 54 — of stray Setpoint-000002 rows appear in the combined export; these are leftovers from
before the database was cleared and are not part of this round.)

## Per-unit results

Figures recomputed directly from the exported CSVs.

| Unit | Mode | Readings | Continuous run | Cadence | In-appliance temp (mean / min) | Dup ts | Status at export |
|---|---|---:|---|---|---|---:|---|
| **Refrigerator-01** | Always-on | **155,990** | **48.65 h, 0 gaps** | ~1/s | +0.24 / **−3.25 °C**, 45.9% sub-zero | 0 (0%) | **Stopped** 07-27 23:01 — operator: battery empty |
| **Freezer** | Duty-cycle | 2,528 | 64.09 h span¹ | ~5 min | **−21.46** / −26.88 °C | 0 (0%) | Last hub delivery 07-28 14:22¹ |
| **Bed Room** | Deep-sleep | 917 | 71.31 h **and counting** | 300 s (91% clean) | 21.96 / 20.50 / 24.25 °C² | 0 (0%) | **Still running** at export |

¹ The freezer opened with a **~9-minute always-on burst** (527 readings, 07-25 22:17) as it cooled from
room temperature, then settled into the ~5-minute cadence. Its last hub-delivered reading is 07-28 14:22
— **7 h before the export**, far longer than one 5-minute cycle — so at export time it was either stopped
or **buffering on-device without delivering** over the metal box's weak Wi-Fi. A pull + full buffer unload
will resolve which (see [next steps](#recommended-next-steps)).

² Bed Room is a room reference, so min/mean/max is the whole-file range (no "in-appliance" filter applies).

## What the temperatures showed (product-value story)

- **Refrigerator runs cold — again.** Mean +0.24 °C but **45.9% of readings were below 0 °C**, dipping to
  **−3.25 °C**. Consistent with Round 1: the hidden sub-freezing swing a logger exists to catch, and this
  time captured at a clean true ~1/s with no dropouts.
- **Freezer is rock-steady:** in-box mean **−21.46 °C**, min **−26.88 °C** — matching Round 1's −21.8 °C
  even at 1/300th the sample density, which is the point of duty-cycle mode.
- **Bedroom** is the calm reference: 21.96 °C, drifting only 20.5–24.3 °C over three days.

## What this round establishes — and does not

| ✔ Established | ✘ Not established |
|---|---|
| A single always-on unit logged **155,990 readings over 48.65 continuous hours** at ~1/s, **0 gaps / 0 dupes**, then stopped. | A **voltage-verified** battery death — no `battery_pct` was logged, so "battery empty" is the operator's read, not a measured cutoff. |
| **Deep-sleep mode works and is frugal:** clean 300-s cadence, still running at **71 h / 3 days**. | **"Weeks per charge."** Three days is not weeks — the deep-sleep unit must run far longer to substantiate it. |
| The **Round 1 duplicate-timestamp defect is fixed** (fridge 4.6%→0%, freezer 1.5%→0%). | Whether the freezer's sparse cadence is **intentional duty-cycle or Wi-Fi-limited delivery** — buffer unload pending. |
| Runtimes fall in the **order battery physics predicts:** always-on (48.6 h) < duty-cycle (64 h+) < deep-sleep (71 h+). | That the ordering is **causal** rather than coincidental — only voltage logging closes that. |

## Recommended next steps

1. **Log battery voltage / SoC as a column** — still the #1 item from Round 1. It is the single change
   that converts every one of these stops from "operator thinks the battery died" into a self-proving
   datapoint at the low-voltage knee.
2. **Let the Bed Room (deep-sleep) unit run until it dies.** It is the "weeks per charge" proof and is
   only ~3 days in. Do not disturb it — its death timestamp is the number that matters.
3. **Freezer: pull it and do a full buffer unload.** This resolves the duty-cycle-vs-Wi-Fi-loss question
   *and* tests on-board buffer integrity (the Round 1 freezer buffer held data). Higher-value right now
   than running it to empty, because its cadence is ambiguous either way.
4. **Record the exact firmware tag** under test so this round is reproducible.

## Listing copy this test supports (safe to use)

> **Field-tested, round two.** A single always-on Setpoint logged **155,990 readings across 48 continuous
> hours** — about one a second — with **zero gaps and zero duplicates**, then ran its battery down. In
> parallel, a deep-sleep unit reported cleanly every five minutes for **three days and counting**.

Keep the always-on figure labelled as **throughput + a single-charge always-on runtime**, present the
battery-empty stop as **operator-observed** (not a measured cutoff), and **do not upgrade the "weeks per
charge" estimate yet** — the deep-sleep run has proven three days, not weeks. The duplicate-timestamp fix
is a clean, demonstrable improvement worth calling out on its own.
