# Field Test #1 — Logging throughput on a single charge

> _First round of full-charge field testing. Three Setpoint units were charged, placed in a
> bedroom, a refrigerator and a freezer, and left logging in **always-on mode (~1 reading/second)**
> until each stopped on its own. Firmware **v2.7.0**, dashboard **2.5.0**. Dates: 2026‑07‑21 → 07‑24._
>
> **Why this doc exists:** [`TINDIE_LISTING.md`](TINDIE_LISTING.md) and
> [`../site/README.md`](../site/README.md) both say the battery claim stays at "weeks" *until a real
> number is confirmed by bench testing*. This is that testing record — and it is deliberately careful
> about what it does and does **not** establish, so the listing copy that draws on it stays honest.

## TL;DR

- **430,022 total readings** were logged across the three units (**421,945** unique timestamps; ~1.9%
  are duplicate-timestamp buffer-flush rows — see [Data quality](#data-quality-notes)).
- The **bedroom unit logged 160,916 readings in one continuous 46.2‑hour session** at ~1 reading/second
  with **zero dropouts** — the cleanest single-charge run and the number safe to lead with.
- This measures **data-capture throughput in the most power-hungry (always-on) mode**. It is **not** a
  measured battery life, and it says **nothing** about the deep-sleep / slow-reporting mode that the
  "weeks per charge" estimate refers to. Battery voltage was not logged, so "ran to empty" is **not**
  established.

## Per-unit results

Figures recomputed directly from the raw exported CSVs (and independently re-derived a second time).

| Unit | Probe ID | Readings | Continuous run | Effective rate | Temp min / mean / max | Dup timestamps |
|---|---|---:|---|---:|---|---:|
| **Bedroom** | Setpoint‑000002 | **160,916** | 46.24 h, **0 gaps** | 0.97 /s | 19.8 / 21.2 / 24.9 °C | 42 (0.03%) |
| **Refrigerator** | Setpoint‑00002F | 129,657 | 50.79 h main run¹ | 0.71 /s | −4.4 / 0.6 / 23.5 °C | 5,924 (4.6%) |
| **Freezer** | Setpoint‑000079 | 139,449² | 41.12 h + 3.6 h¹ | 0.87 /s | −27.3 / −21.8 / 23.3 °C | 2,111 (1.5%) |
| **Total** | — | **430,022** | — | — | — | 8,077 (1.9%) |

¹ The refrigerator and freezer files contain multi‑hour gaps near the end. Those gaps are **deliberate**:
after each unit stopped, it was powered back on later to check its on‑board buffer. The refrigerator's
buffer was empty; the freezer's still held data that was only **partially** unloaded — so the freezer
count is a **conservative floor**, and the room‑temperature "tails" in both files are the buffer‑check
power‑ons, not appliance readings.

² Effective rates below 1/s on the two cold units reflect occasional 4–5 s intervals plus the
duplicate‑timestamp rows; only the bedroom unit sampled at a true ~1/s throughout. (First minutes of
every run were at a 5 s cadence before settling to 1 s.)

## What the temperatures showed (product‑value story)

- **Refrigerator runs cold.** Mean +0.6 °C, but **45% of readings were below 0 °C**, dipping to
  **−4.4 °C** — the kind of hidden sub‑freezing swing (produce/eggs at risk) that a logger exists to
  catch.
- **Freezer is rock‑steady:** mean −21.9 °C, min −27.3 °C, **99.8%** of the time below 0 °C, with clean
  repeating defrost/compressor cycles resolved at 1‑second detail (roughly a half‑dozen or more per day
  — exact count depends on the detection threshold, so we don't quote a hard number).
- **Bedroom** is a calm reference: 21.2 °C ± 0.5 °C, slow daily drift only.

## Data quality notes (for the firmware update in progress)

- **Duplicate timestamps concentrate in the cold units** (fridge 4.6%, freezer 1.5%, bedroom 0.03%).
  The pattern tracks weak 2.4 GHz Wi‑Fi inside metal appliances → more reconnects → buffer re‑flush
  replaying rows. No **backwards** timestamps in any file (RTC stays monotonic). Worth de‑duplicating on
  ingest and/or fixing the flush‑dedupe path in firmware.
- The exported `humidity_pct` / `vpd_kpa` columns are **empty** (temperature‑only probes) — expected,
  but the export carries the unused columns.

## What this round does — and does not — establish

| ✔ Established | ✘ Not established |
|---|---|
| A single unit captured **160,916 readings over 46 continuous hours** at ~1/s with zero dropouts. | A **measured battery life** — no voltage/SoC was logged, so "ran to empty" is unproven. |
| **1‑second capture** resolves defrost cycles and sub‑freezing dips a periodic logger would miss. | The **deep‑sleep / "weeks per charge"** figure — that mode was **not exercised** at all. |
| **On‑board buffering** retains readings through a hub/Wi‑Fi outage (freezer buffer held data). | That the two cold units logged **perfectly continuously** — both had interruptions. |

## Recommended next round (to make a real battery claim)

1. **Log battery voltage** (or coulomb count) as a column, so a run can be shown to end at the
   low‑voltage cutoff rather than a comms/manual event.
2. Run **deep‑sleep / slow‑interval** units in parallel — that is the configuration the "weeks per
   charge" claim needs, and this test never touched it.
3. Hold a **constant bench temperature** with strong stable Wi‑Fi, ≥3 units, no human intervention until
   firmware logs a brownout; capture the terminal‑voltage knee.
4. Fix the **duplicate‑timestamp** flush path, then re‑measure clean throughput.

## Listing copy this test supports (safe to use)

> **Field‑tested.** In its first full‑charge test, a single Setpoint logged **160,916 readings in one
> continuous 46‑hour session** — about one every second, always‑on — with nothing dropped. Three units
> captured **430,000+** readings in the round.

Keep the **"always‑on / once a second"** qualifier next to any runtime number, present it as
**data‑capture throughput** (not battery life), and leave the **"weeks per charge"** estimate as the
separate, still‑pending deep‑sleep figure it describes.
