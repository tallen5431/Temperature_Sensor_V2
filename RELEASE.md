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

**Firmware** — only when the `.ino` actually changed. All four must agree, and
the last three are enforced against the first:

- `esp32_temp_probe/esp32_temp_probe.ino` — `FW_VERSION` *(the source of truth)*
- `firmware/src/protocol.h` — `TEMPSENSOR_FW_VERSION`
- `flash/manifest.json` — `version`
- `flash/index.html` — the `firmware v…` label

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

Ship the source zip customers run with `Start.bat` / `Start.sh`, or produce a
one-file Windows executable:

```
pip install pyinstaller
pyinstaller --onefile --name Setpoint app.py
```

(Bundle `config.example.json` and `assets/` alongside the binary.) Smoke-test the
build: launch it, open http://localhost:8088, confirm the footer shows the new
version and `GET /api/health` reports it.

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
