# Release Runbook

A lightweight, solo-maker checklist for cutting a TempSensor release and shipping
a batch of TempSensor units. Do the steps in order; each release is one version
number applied consistently to the hub, the firmware, and the store listing.

## 1. Bump the version

Pick the new version (SemVer) and set it in **all** of these — they must match:

- `core/version.py` — `__version__`
- `pyproject.toml` — `[project] version`
- `firmware/src/protocol.h` — `TEMPSENSOR_FW_VERSION`

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
git tag -a vX.Y.Z -m "TempSensor vX.Y.Z"
git push && git push --tags
```

## 5. Build the hub

Ship the source zip customers run with `Start.bat` / `Start.sh`, or produce a
one-file Windows executable:

```
pip install pyinstaller
pyinstaller --onefile --name TempSensor app.py
```

(Bundle `config.example.json` and `assets/` alongside the binary.) Smoke-test the
build: launch it, open http://localhost:8080, confirm the footer shows the new
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
