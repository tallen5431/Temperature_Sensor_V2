# Packaging the Temperature Hub

Build a **single self-contained executable** so customers run the hub without
installing Python. Built with [PyInstaller](https://pyinstaller.org/).

## Build

Build on the **same OS** you want to ship to (PyInstaller does not cross-compile).

**Linux / macOS**
```bash
./packaging/build.sh
# -> dist/temperature-hub
```

**Windows**
```bat
packaging\build.bat
REM -> dist\temperature-hub.exe
```

Then just run the binary and open <http://localhost:8088>.

### Where data lives
When frozen, the hub writes `config.json`, `temperature_log.db`, and `logs/`
**next to the executable** (not inside the temp bundle), so data persists across
restarts. Override with the `DATA_DIR` environment variable. The bundled
`config.example.json` seeds `config.json` on first run.

## Install as a service (auto-start on boot, restart on crash)

### Linux (systemd)
```bash
sudo mkdir -p /opt/temperature-hub
sudo cp dist/temperature-hub /opt/temperature-hub/
sudo cp packaging/systemd/temperature-hub.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now temperature-hub
journalctl -u temperature-hub -f      # view logs
```

### Windows (service)
The simplest reliable option is [NSSM](https://nssm.cc/):
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

## Notes & troubleshooting
- **Antivirus / SmartScreen:** unsigned executables may be flagged. For a real
  product, code-sign the binary (Windows Authenticode / Apple notarization).
- **Size:** the bundle is large (~150–300 MB) because it includes Python, Dash,
  Plotly, and pandas. That's expected for a one-file build.
- **Firewall:** allow the binary on private networks so probes can reach it and
  mDNS works (UDP 5353, TCP 8088).
- If a lazily-imported module is missing at runtime, add it to `hiddenimports`
  in `packaging/temperature_hub.spec`.
