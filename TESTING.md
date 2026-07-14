# Testing Guide

How to test the Temperature Hub + probes to find regressions early and ship a
product you can trust. Work top-down: the automated suite catches logic bugs in
seconds; the hardware and resilience sections catch the things that actually bite
customers in the field.

---

## 1. Automated tests (run these constantly)

```bash
pip install -r requirements-dev.txt
pytest                 # whole suite, ~1s
pytest -k notifications -v
pytest --cov=core --cov=api --cov-report=term-missing   # after: pip install pytest-cov
```

What's covered today (`tests/`):

| Area | File | Why it matters |
|---|---|---|
| SQLite store | `test_db.py` | windowing, downsampling, stats, retention, backup, migration |
| Ingest/normalisation | `test_storage.py` | unit parsing, **timezone conversion** (the historically buggy part) |
| REST API | `test_api.py` | ingest, auth, secret redaction, **calibration** |
| Alert engine | `test_alerts.py` | transitions, cooldown, recovery — no false repeats |
| Notifications | `test_notifications.py` | email/webhook with mocked SMTP/HTTP, isolated channel failures |
| Alert monitor | `test_alert_monitor.py` | fires once, dedupes, ignores stale, recovery |
| Settings logic | `test_settings.py` | cooldown maths, password-preserve |
| Dashboard compute | `test_dashboard.py` | multi-probe graph, °C/°F, alert rendering |

**When you add a feature, add a test in the same PR.** CI (`.github/workflows/ci.yml`)
runs the suite on Python 3.9 and 3.12 on every push.

Good next additions: `pytest-cov` to track coverage, and `hypothesis` for
property-testing `normalize_payload` / `iso_to_epoch` against random timestamps.

---

## 2. Hardware-in-the-loop (the real product test)

These need a flashed ESP32 + DS18B20 and can't be faked. Keep a written log of
pass/fail per firmware version.

**First-time provisioning**
- [ ] Power a probe with no saved Wi-Fi → it starts the `Setpoint-XXXX` SoftAP.
- [ ] Join it, set home Wi-Fi at `192.168.4.1`, save.
- [ ] Within ~20 s the probe appears on the hub **Devices** page and readings start.
- [ ] Settings → Probe Setup Helper detects the SoftAP SSID.

**Accuracy & calibration**
- [ ] Compare the probe against a reference thermometer in ice water (0 °C) and
      body-temp/warm water. Record the error.
- [ ] Enter the offset in Devices → Edit → Calibration; confirm stored readings shift.

**Sleep / battery**
- [ ] Interval ≥ 10 s → device deep-sleeps (`/status` shows `sleep_mode: deep`,
      wake count climbs). Measure idle current (should drop to ~mA).
- [ ] Interval < 10 s → stays in modem sleep, web server stays responsive.
- [ ] Change interval from the hub and confirm the probe picks it up within a cycle.

**Time correctness** (this has bitten before)
- [ ] Readings on the graph match wall-clock **local** time, not UTC.
- [ ] Set the hub PC to a non-UTC timezone and re-check the graph + CSV export.
- [ ] Cross a DST boundary (or fake the clock) and confirm no jump/duplication.

---

## 3. Resilience / failure injection (where products break)

Simulate the bad day a customer will eventually have:

- [ ] **Hub down while probe runs:** stop the hub for 10 min, keep the probe
      powered. Readings buffer to LittleFS (`/status` → `buffered_est_rows` rises).
      Restart the hub → buffered readings flush in order, no gaps, no duplicates.
- [ ] **Probe power-cut mid-write:** pull power repeatedly. On reboot the buffer
      resumes from the saved offset; the dashboard never goes blank.
- [ ] **Wi-Fi drop:** disable the AP for a few minutes; probe reconnects and flushes.
- [ ] **DHCP IP change:** force the probe to a new IP (reboot router) — the
      auto-provisioner re-resolves and keeps delivering.
- [ ] **Hub restart:** confirm data persists (SQLite), the device list repopulates,
      and online/offline status is correct after `probe_online_timeout_sec`.
- [ ] **Corrupt/garbage ingest:** `curl` a bad payload → API returns 400, no crash.

---

## 4. Notifications (verify the alerting product actually alerts)

- [ ] Set a tight max threshold on a probe, warm the sensor → email/webhook arrives.
- [ ] Confirm you get **one** alert, not one every poll (cooldown works).
- [ ] Leave it breached past the reminder interval → exactly one reminder.
- [ ] Let it return to normal → recovery message (if enabled).
- [ ] **Send test** button works for each channel; a wrong SMTP password reports a
      clear failure, and a broken webhook doesn't block email.
- [ ] Kill a probe while it's breached → decide if you want an "offline" alert
      (currently you don't get one — see roadmap).

Quick local webhook receiver for testing without Slack:
```bash
python -m http.server 9000   # or a tiny POST echo; point the webhook at it
```

---

## 5. Soak & load (does it hold up over weeks?)

- [ ] Run 5–10 probes (or simulate with a loop of `curl /api/ingest`) for 48 h.
- [ ] Watch hub memory/CPU — should stay flat (windowed queries, not full re-reads).
- [ ] Let the DB grow large, then set `retention_days` and confirm old rows purge
      and disk stops growing.
- [ ] Dashboard stays responsive on "All Time" with a big DB (downsampling).
- [ ] Download a backup of a large DB — streams without spiking memory.

Simulate many probes:
```bash
for p in $(seq 1 10); do
  ( while true; do
      curl -s "http://localhost:8088/api/ingest?temperature_c=$((RANDOM%40))&probe_id=SIM-$p" >/dev/null
      sleep 2
    done ) &
done
```

---

## 6. Cross-platform & install

- [ ] `Start.bat` on Windows and `Start.sh` on macOS/Linux: clean machine, only
      Python installed → first run creates the venv, second run skips the install
      (fast). Browser opens to the dashboard.
- [ ] Windows Firewall / mDNS: probes still discovered, or readings still arrive by
      direct POST if mDNS is blocked.
- [ ] Fresh clone has **no** `config.json` → it's seeded from `config.example.json`
      with empty names/thresholds (no leftover demo data).

## 7. Security

- [ ] Set `SERVER_TOKEN` → ingest/provision/config without the token return 401;
      with it, succeed. Probes get re-provisioned with the token automatically.
- [ ] `GET /api/config` never returns the real `provision_token`/SMTP password
      (shows `***set***`).

---

## Pre-release checklist (run before every firmware/hub release)

1. `pytest` green on 3.9 and 3.12 (CI).
2. Fresh-install smoke on Windows **and** Linux.
3. One full provisioning → reading → alert → recovery loop on real hardware.
4. One power-cut + hub-down buffering/flush cycle with no data loss.
5. Timezone + DST sanity check.
6. Bump `core/version.py` (hub) / `FW_VERSION` (firmware) and update `CHANGELOG.md`.
