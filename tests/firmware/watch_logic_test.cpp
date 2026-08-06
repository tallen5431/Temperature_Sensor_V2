// Extracts the pure decision logic added to esp32_temp_probe.ino and exercises
// it on the host. This is the part of a firmware change that can be verified
// without a probe: the arithmetic and the state machine. Radio behaviour, power
// draw and NVS wear still need the bench.
#include <cstdio>
#include <cstdint>
#include <cassert>
#include <initializer_list>

// ---- verbatim from the .ino -------------------------------------------------
static const float    WATCH_UNSET_C       = -999.0f;
static const float    WATCH_HYSTERESIS_C  = 0.5f;
static const uint32_t WATCH_SAMPLE_MIN_MS = 5000UL;

float    cfg_alert_min_c = WATCH_UNSET_C;
float    cfg_alert_max_c = WATCH_UNSET_C;
uint32_t cfg_sample_ms   = 0;
uint32_t cfg_interval    = 5000;
bool     rtc_inBreach    = false;
uint32_t rtc_msSinceReport = 0;

static bool watchArmed() {
  bool haveLimit = (cfg_alert_min_c > WATCH_UNSET_C) || (cfg_alert_max_c > WATCH_UNSET_C);
  return haveLimit && cfg_sample_ms >= WATCH_SAMPLE_MIN_MS && cfg_sample_ms < cfg_interval;
}

static bool outsideLimits(float tC) {
  const float slack = rtc_inBreach ? WATCH_HYSTERESIS_C : 0.0f;
  if (cfg_alert_max_c > WATCH_UNSET_C && tC > cfg_alert_max_c - slack) return true;
  if (cfg_alert_min_c > WATCH_UNSET_C && tC < cfg_alert_min_c + slack) return true;
  return false;
}

// The watchArmed() branch of the deep-sleep duration, from the bottom of loop().
// This decides how often the probe wakes, which is battery life, and how late a
// report lands. It had no test at all.
static uint32_t watchSleepMs(uint32_t elapsed) {
  uint32_t untilReport = rtc_msSinceReport < cfg_interval
                         ? cfg_interval - rtc_msSinceReport : 0UL;
  uint32_t gap = cfg_sample_ms < untilReport ? cfg_sample_ms : untilReport;
  if (untilReport == 0UL) gap = cfg_sample_ms;   // report just fired
  return gap > elapsed ? (gap - elapsed) : 100UL;
}
// ---- end verbatim -----------------------------------------------------------

static int failures = 0;
#define CHECK(cond, msg) do { if(!(cond)) { printf("  FAIL: %s\n", msg); failures++; } } while(0)

// Feed a temperature through the same transition test loop() uses.
// Returns true when this reading would trigger an unscheduled transmission.
static bool step(float tC) {
  bool breach = outsideLimits(tC);
  bool transition = (breach != rtc_inBreach);
  rtc_inBreach = breach;
  return transition;
}

int main() {
  printf("arming\n");
  cfg_interval = 900000; cfg_sample_ms = 0;
  cfg_alert_min_c = WATCH_UNSET_C; cfg_alert_max_c = WATCH_UNSET_C;
  CHECK(!watchArmed(), "no limits must not arm");
  cfg_alert_max_c = -15.0f;
  CHECK(!watchArmed(), "limit but no sample cadence must not arm");
  cfg_sample_ms = 60000;
  CHECK(watchArmed(), "limit + shorter sample cadence must arm");
  cfg_sample_ms = 900000;
  CHECK(!watchArmed(), "sample cadence == report interval is pointless, must not arm");
  cfg_sample_ms = 1000;
  CHECK(!watchArmed(), "sample cadence below the floor must not arm");
  cfg_sample_ms = 60000;

  printf("a freezer thawing slowly (limit -15)\n");
  rtc_inBreach = false;
  cfg_alert_min_c = WATCH_UNSET_C; cfg_alert_max_c = -15.0f;
  float slow[] = {-18.0f, -17.6f, -17.1f, -16.5f, -15.9f, -15.2f, -14.8f, -14.0f, -12.0f};
  int fired = 0, firedAt = -1;
  for (int i = 0; i < 9; i++) if (step(slow[i])) { fired++; firedAt = i; }
  CHECK(fired == 1, "a slow thaw must transmit exactly once, on crossing");
  CHECK(firedAt == 6, "must fire at the first reading past -15.0 (-14.8)");
  printf("  fired once at reading %d (%.1f C)\n", firedAt, slow[firedAt]);

  printf("parked on the limit must not chatter\n");
  rtc_inBreach = false;
  int chatter = 0;
  float jitter[] = {-14.9f, -15.05f, -14.95f, -15.1f, -14.9f, -15.02f};
  for (int i = 0; i < 6; i++) if (step(jitter[i])) chatter++;
  CHECK(chatter == 1, "hysteresis must swallow jitter around the limit");
  printf("  transmissions across 6 jittering samples: %d\n", chatter);

  printf("recovery needs to beat the limit by the deadband\n");
  rtc_inBreach = false;
  CHECK(step(-14.0f), "entering breach fires");
  CHECK(!step(-15.2f), "back inside but within the deadband must NOT clear yet");
  CHECK(step(-15.6f), "clearly recovered must fire the all-clear");
  CHECK(!rtc_inBreach, "state must be clear after recovery");

  printf("a cooler with both limits (0..8)\n");
  rtc_inBreach = false;
  cfg_alert_min_c = 0.0f; cfg_alert_max_c = 8.0f;
  CHECK(!step(4.0f), "in spec, no transmission");
  CHECK(step(8.4f),  "over the top limit fires");
  CHECK(!step(7.7f), "inside the deadband does not clear");
  CHECK(step(7.2f),  "clear of the deadband clears");
  CHECK(step(-0.4f), "under the bottom limit fires");
  CHECK(step(0.8f),  "back above the bottom limit clears");

  printf("a one-sided limit ignores the other end\n");
  rtc_inBreach = false;
  cfg_alert_min_c = WATCH_UNSET_C; cfg_alert_max_c = 8.0f;
  CHECK(!step(-40.0f), "no min limit means arbitrarily cold is not a breach");
  CHECK(step(9.0f), "the max limit still applies");

  // --- how long to sleep, which is battery life and report punctuality ------
  printf("sleeping to the next sample, but never past the report\n");
  cfg_interval = 900000; cfg_sample_ms = 60000;
  const uint32_t awake = 300;

  rtc_msSinceReport = 0;
  CHECK(watchSleepMs(awake) == 60000 - awake, "a full sample gap when the report is far off");

  rtc_msSinceReport = 840000;                     // exactly one sample to go
  CHECK(watchSleepMs(awake) == 60000 - awake, "one sample left sleeps one sample");

  rtc_msSinceReport = 890000;                     // 10 s to the report
  CHECK(watchSleepMs(awake) == 10000 - awake, "a short remainder is honoured");

  // The regression. `if (gap < WATCH_SAMPLE_MIN_MS)` also fired for any
  // remainder of 1..4999 ms, undoing the clamp above it: the probe slept a
  // whole sample gap and the report landed up to cfg_sample_ms late, every
  // cycle, whenever cfg_interval % cfg_sample_ms fell in that band.
  printf("a remainder under the sample floor must not delay the report\n");
  // The property is that the probe never sleeps a WHOLE SAMPLE GAP when only a
  // short remainder is left — not that it hits the deadline exactly, which it
  // cannot: a remainder shorter than the wake itself floors at 100 ms, and no
  // probe can report sooner than it takes to wake and read the sensor.
  for (uint32_t left : {1u, 100u, 3000u, 4999u}) {
    rtc_msSinceReport = cfg_interval - left;
    uint32_t s = watchSleepMs(awake);
    uint32_t bound = left > 100UL ? left : 100UL;
    CHECK(s <= bound, "slept past the report when a shorter remainder was left");
    if (s > bound)
      printf("    left=%u ms -> slept %u ms (report %u ms late)\n",
             left, s, s + awake - left);
  }

  printf("a report that is already due sleeps a sample, not zero\n");
  rtc_msSinceReport = cfg_interval;               // due now
  CHECK(watchSleepMs(awake) == 60000 - awake, "report due must sleep one sample gap");
  rtc_msSinceReport = cfg_interval + 5000;        // overshot
  CHECK(watchSleepMs(awake) == 60000 - awake, "an overshoot must not underflow");

  printf("the sleep never collapses to zero\n");
  rtc_msSinceReport = 0;
  CHECK(watchSleepMs(999999) == 100UL, "a wake longer than the gap floors at 100 ms");

  printf("\n%s\n", failures ? "FAILURES ABOVE" : "all watch-logic checks passed");
  return failures ? 1 : 0;
}
