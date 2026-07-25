# Field Test #2 — Battery runtime + firmware-2.8.0 verification (plan)

Two goals this round:

1. **Confirm the fw 2.8.0 fixes on hardware** — no duplicate timestamps, fast
   buffer drain, clean recharge/rejoin (no rogue setup AP).
2. **First real deep-sleep runtime numbers** across three temperatures, run to
   depletion.

Firmware **v2.8.0**. Follows [`BATTERY_FIELD_TEST.md`](BATTERY_FIELD_TEST.md)
(Field Test #1, always-on 1 s throughput).

> **Honesty caveat (carry from FT#1):** with no battery-voltage column yet,
> "runtime" = **last good reading − start** = runtime-**to-silence**, not a
> measured run-to-empty at the low-voltage cutoff. Report it exactly that way.

---

## The run matrix (4 probes, run to depletion)

| Run | Location | Mode | Interval | Why this cell |
|-----|----------|------|----------|---------------|
| **A** | Refrigerator | always-on | **1 s** | Fix check (dupes / fast drain, weak in-appliance Wi-Fi) **+** always-on runtime |
| **B** | Refrigerator | deep-sleep | **5 min** | Deep-sleep runtime (cold); direct A/B vs A in the **same** fridge |
| **C** | Freezer | deep-sleep | **5 min** | Coldest runtime — cold worst-case battery |
| **D** | Bedroom | deep-sleep | **5 min** | Best-case runtime — **the headline "weeks" number** |

Notes:
- Keep **resolution identical on all four** (11-bit is a good default) so the only
  variables are interval/mode and temperature.
- **A** drains fast (~2 days always-on) and gives the fix check in its first hours —
  you don't wait for it to die to learn the fix worked.
- **D** lasts longest and is the number you quote for the listing.
- **C** dies earliest from the cold — that's lithium chemistry (reduced capacity +
  higher internal resistance at −20 °C), **not a defect**. Don't let it stand in
  for the product's battery life.

---

## Keep it clear: label by role, not just probe ID

The probe's **friendly name travels into the CSV export**, so the cleanest way to
keep four concurrent runs straight is to name each probe by its run in the
dashboard. Then every export is self-labeling — no cross-referencing later.

- **Devices → Edit friendly name**, e.g.: `FT2-A Fridge 1s`, `FT2-B Fridge 5m`,
  `FT2-C Freezer 5m`, `FT2-D Bedroom 5m`.
- Record the config that the CSV does **not** carry (interval, resolution, start
  time, ambient) in the run log below.

### Run log (fill in as you go)

| Run | Probe ID | Friendly name | Interval | Res | Start (local) | Last reading | Runtime | Notes |
|-----|----------|---------------|----------|-----|---------------|--------------|---------|-------|
| A   |          |               | 1 s      |     |               |              |         |       |
| B   |          |               | 5 min    |     |               |              |         |       |
| C   |          |               | 5 min    |     |               |              |         |       |
| D   |          |               | 5 min    |     |               |              |         |       |

---

## Checks — don't wait for depletion

- [ ] All four report **`fw_version` 2.8.0** at `/whoami` (tap **reset** to wake a
      deep-sleeper for the check).
- [ ] **Run A, first day:** export the CSV and confirm **no repeated
      `(timestamp, probe_id)`** rows, and that the buffer drains fast after any
      Wi-Fi drop. ← this is the 2.8.0 duplicate/drain-fix proof.
- [ ] Any probe re-powered mid-run **rejoins Wi-Fi on its own** — no
      `Setpoint-XXXXXX` setup network. ← the recharge-rejoin fix.
- [ ] Deep-sleepers (B/C/D) clearly **outlast** A — confirms deep sleep engaged.

---

## If you'd rather actively experiment with two probes

The freezer/bedroom probes can instead be a **swap slot** for shorter experiments
(resolution comparison, later the decoupled sample/upload prototype). If so:

- Keep **A + B** (the fridge pair) as the run-to-depletion anchor — fix check +
  cold deep-sleep A/B.
- **But preserve one room-temp, strong-Wi-Fi 5-min run to depletion** somewhere
  (i.e. don't sacrifice Run D's role) — it's the only clean "weeks" number you'll
  be able to quote.

---

## What this round feeds

- **Clearing fw 2.8.0 to merge** — Run A's fix check + B/C/D deep-sleep & rejoin
  behavior are the hardware validation the firmware PR is waiting on.
- **The listing battery figure** — Run D, framed as runtime-to-silence.
- **Field Test #3** — add the battery-voltage divider (see
  [`PRODUCT_ROADMAP.md`](PRODUCT_ROADMAP.md) → Firmware/hardware backlog) and
  re-run for a true run-to-empty at the cutoff knee.
