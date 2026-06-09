# Contributing

Thanks for helping improve the Temperature Hub. This guide covers the hub (the
Python PC-side app) and the ESP32 probe firmware.

## Development setup

```bash
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest                          # whole suite, ~3 s
```

Run the hub from source while developing:

```bash
python app.py                   # serves http://localhost:8088
```

## Ground rules

- **Add a test with every behaviour change.** The suite lives in `tests/` and
  runs on Python 3.9 and 3.12 in CI on every push and PR. Pure logic
  (alerts, config validation, status, diagnostics, discovery de-dup) is unit
  tested directly — keep new logic pure and testable where you can.
- **Log, don't print.** Use a module logger
  (`logging.getLogger("hub.<area>")`); `print()` is lost in the packaged
  no-console build. See `core/logging_setup.py`.
- **Never break a bad config.** User-facing settings flow through
  `core/config_schema.normalize_config`; extend it (with a test) when you add a
  config field, so a hand-edited `config.json` can't crash the hub.
- **Don't leak secrets.** `GET /api/config` and `/api/diagnostics` must never
  expose tokens, passwords, SMTP hosts, or webhook URLs. There are tests that
  assert this — keep them green.
- **Match the surrounding style.** Small, focused functions; type hints on new
  public functions; docstrings that say *why*.

## Branch & PR flow

1. Branch from the default branch.
2. Make the change + tests; run `pytest` locally.
3. Update `CHANGELOG.md` (and `README.md` if user-facing).
4. Open a PR using the template. CI must be green before merge.

## Firmware

The probe firmware is a single sketch: `esp32_temp_probe/esp32_temp_probe.ino`,
versioned independently via `FW_VERSION`. It needs the Arduino ESP32 core plus
WiFiManager, ArduinoJson, DallasTemperature + OneWire (see the header comment).
Bump `FW_VERSION` for any behaviour change and note it in `CHANGELOG.md`.

## Where things live

| Area | Path |
|---|---|
| Entry point / wiring | `app.py` |
| REST API | `api/routes.py` |
| Data store (SQLite) | `core/db.py` |
| Alerts / notifications | `core/alerts.py`, `core/notifications.py`, `alert_monitor.py` |
| Config + validation | `core/config.py`, `core/config_schema.py` |
| Discovery / provisioning | `probe_discovery.py`, `provisioning.py`, `provisioner.py` |
| UI panels | `components/` |
| Tests | `tests/` |

See [TESTING.md](TESTING.md) for the full manual + hardware test plan.
