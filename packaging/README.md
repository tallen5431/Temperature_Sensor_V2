# Packaging the Temperature Hub

Build a **self-contained folder** customers can run without installing Python.
Built with [PyInstaller](https://pyinstaller.org/).

This is a **onedir** build: the output is `dist/temperature-hub/` containing the
`temperature-hub` executable plus an `_internal/` folder of dependencies. Onedir
(rather than one-file) keeps the LGPL-licensed `zeroconf` module as replaceable
files on disk, which cleanly satisfies LGPL's "user may modify and relink"
requirement — see [`../THIRD-PARTY-LICENSES.md`](../THIRD-PARTY-LICENSES.md).
Ship the **whole folder**, not just the executable.

## Build

Build on the **same OS** you want to ship to (PyInstaller does not cross-compile).
The build refreshes `THIRD-PARTY-LICENSES.md` from the exact versions it bundles,
and copies `LICENSE` + `THIRD-PARTY-LICENSES.md` into the distribution folder.

**Linux / macOS**
```bash
./packaging/build.sh
# -> dist/temperature-hub/   (run dist/temperature-hub/temperature-hub)
```

**Windows**
```bat
packaging\build.bat
REM -> dist\temperature-hub\   (run dist\temperature-hub\temperature-hub.exe)
```

Then run the executable and open <http://localhost:8088>.

### Where data lives
When frozen, the hub writes `config.json`, `temperature_log.db`, and `logs/`
**next to the executable** (inside the distribution folder), so data persists
across restarts. Override with the `DATA_DIR` environment variable (recommended
for service installs — point it at a dedicated writable directory). The bundled
`config.example.json` seeds `config.json` on first run.

## Install as a service (auto-start on boot, restart on crash)

### Linux (systemd)
```bash
sudo mkdir -p /opt/temperature-hub
sudo cp -r dist/temperature-hub/* /opt/temperature-hub/   # the whole folder
sudo cp packaging/systemd/temperature-hub.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now temperature-hub
journalctl -u temperature-hub -f      # view logs
```

### Windows (service)
The simplest reliable option is [NSSM](https://nssm.cc/). Copy the whole
`dist\temperature-hub\` folder to `C:\Program Files\TemperatureHub\`, then:
```bat
nssm install TemperatureHub "C:\Program Files\TemperatureHub\temperature-hub.exe"
nssm set TemperatureHub AppDirectory "C:\Program Files\TemperatureHub"
nssm start TemperatureHub
```
Or, without extra tools, create a Task Scheduler task set to "Run whether user is
logged on or not" with trigger "At startup".

### macOS (launchd)
Create `~/Library/LaunchAgents/com.yourbrand.temperaturehub.plist` with a
`ProgramArguments` pointing at the binary and `RunAtLoad`/`KeepAlive` set to true,
then `launchctl load` it.

## Licensing in the distribution
The build copies `LICENSE` (proprietary) and `THIRD-PARTY-LICENSES.md` into the
distribution folder. Keep both with anything you ship — `THIRD-PARTY-LICENSES.md`
is what satisfies the bundled open-source components' terms, including the LGPL
source offer for `zeroconf`. Regenerate it any time with
`python packaging/gen_third_party_licenses.py`.

## Notes & troubleshooting
- **Antivirus / SmartScreen:** unsigned executables may be flagged. For a real
  product, code-sign the executable (Windows Authenticode / Apple notarization).
- **Size:** the folder is large (~150–300 MB) because it includes Python, Dash,
  Plotly, and pandas. That's expected.
- **Firewall:** allow the executable on private networks so probes can reach it
  and mDNS works (UDP 5353, TCP 8088).
- If a lazily-imported module is missing at runtime, add it to `hiddenimports`
  in `packaging/temperature_hub.spec`.
