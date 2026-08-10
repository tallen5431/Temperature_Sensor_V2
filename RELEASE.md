# Release Runbook

A lightweight, solo-maker checklist for cutting a Setpoint release and shipping
a batch of Setpoint units. Do the steps in order; each release is one version
number applied consistently to the hub, the firmware, and the store listing.

## 1. Bump the version

**The hub and the firmware version independently.** They are separate artifacts
on separate cadences — a dashboard fix does not reflash anybody's probes — so
they are two lists, not one, and they do not have to match.

**Hub** (both must agree; `tests/test_version_sync.py` enforces it):

- `core/version.py` — `HUB_VERSION`
- `pyproject.toml` — `[project] version`

**Firmware** — only when the `.ino` actually changed. All of these must agree,
and every one of them is enforced against the first:

- `esp32_temp_probe/esp32_temp_probe.ino` — `FW_VERSION` *(the source of truth)*
- `firmware/src/protocol.h` — `TEMPSENSOR_FW_VERSION`
- `flash/manifest.json` — `version`
- `flash/index.html` — the `firmware v…` label
- `docs/QC_CHECKLIST.md` — the version the factory gate compares `/whoami` to
- `web/guide.html` — the version the deployed build guide advertises

`firmware/factory_flash.py` needs no edit: it reads `FW_VERSION` out of the
`.ino` at import. It used to hold a literal, and that literal is how the
physical label and the QC gate came to name 2.8.2 while the sketch shipped
2.9.3 — so every unit built would have failed its own `/whoami` check.

> This list used to name `protocol.h` and omit `flash/manifest.json` and
> `flash/index.html` — exactly backwards from what the tests check. Following it
> moved the one copy nothing verified and left the two that are verified behind,
> which is how the flash manifest went stale twice and how `protocol.h` came to
> sit on 2.8.2 while the `.ino` was on 2.9.2. `pytest -q` now catches all of it,
> so run step 3 before tagging and believe it over this list.

If the wire protocol changed, also bump `PROTOCOL_VERSION` in `core/version.py`
and `TEMPSENSOR_PROTO` in `firmware/src/protocol.h` (keep them equal).

## 2. Update the changelog

Move the pending notes into a new dated section in `CHANGELOG.md`
(`## [x.y.z] - YYYY-MM-DD`, Keep a Changelog format).

## 3. Test

```
pip install -r requirements-dev.txt
pytest -q
```

All tests must pass. CI (`.github/workflows/ci.yml`) runs the same on push/PR —
green there before tagging.

## 4. Tag

```
git commit -am "Release vX.Y.Z"
git tag -a vX.Y.Z -m "Setpoint vX.Y.Z"
git push && git push --tags
```

## 5. Build the hub

Ship the source zip customers run with `Start.bat` / `Start.sh`, or produce the
self-contained bundle — **the whole `dist/temperature-hub/` folder**, not just
the executable inside it:

```
./packaging/build.sh          # Linux / macOS
packaging\build.bat           # Windows
# both run: pyinstaller --clean --noconfirm packaging/temperature_hub.spec
```

Always the spec, never a bare `pyinstaller --onefile`. Two reasons, and the
first is a licence term:

* `THIRD-PARTY-LICENSES.md` promises that the LGPL-licensed `zeroconf` module
  ships as replaceable files under `_internal/`, so a user can modify and
  relink it. `--onefile` bundles it into the executable and breaks that
  commitment on every copy shipped.
* The spec carries the `datas` the app loads at runtime (`assets/`,
  `config.example.json`, `LICENSE`, `THIRD-PARTY-LICENSES.md`) and the
  `hiddenimports` (paho-mqtt and friends) that a bare invocation drops — so a
  `--onefile` build starts with no stylesheet and no MQTT.

Smoke-test the build: launch it, open http://localhost:8088, confirm the footer
shows the new version and `GET /api/health` reports it.

## 6. Flash + QC the probe batch

Flash each unit and run it through the manufacturing gate:

```
python firmware/factory_flash.py
```

Every unit must PASS every line of [QC_CHECKLIST](docs/QC_CHECKLIST.md); record
each unit in the serial-log CSV so shipped hardware stays traceable.

## 7. Publish

- Attach the hub build (zip / installer) to the release.
- Update the store listing with the new version, changelog highlights, and any
  new screenshots.
- Announce.
