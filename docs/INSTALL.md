# Installing the TempSensor hub

The hub is the small app that collects readings from your probes and shows the
dashboard. Install it on any always-on computer (a laptop, a mini-PC, a Raspberry
Pi) on the same network as your probes. You do **not** need to install Python.

Download the installer for your system from the
[**Releases**](https://github.com/tallen5431/Temperature_Sensor_V2/releases)
page, then follow the steps below. When it starts, the dashboard opens in your
browser automatically at <http://localhost:8088>.

---

## Windows

1. Download **`TempSensor-Setup-<version>.exe`**.
2. Double-click it and follow the installer. It installs just for you (no admin
   password needed) and offers to add a desktop shortcut and to start
   automatically when you sign in.
3. Launch **TempSensor** from the Start menu (or the desktop). The dashboard
   opens in your browser.

> **"Windows protected your PC" (SmartScreen)?** This appears for apps that
> aren't signed with a paid certificate. Click **More info → Run anyway**. (Signed
> releases won't show this.)

Your data (settings, readings, logs) is stored in
`%LOCALAPPDATA%\TempSensor`.

## macOS

1. Download **`TempSensor-<version>.dmg`**.
2. Open the `.dmg` and drag **TempSensor** to your Applications folder.
3. Launch **TempSensor**. The dashboard opens in your browser.

> **"TempSensor can't be opened because Apple cannot check it…"?** This appears
> for apps that aren't notarized. **Right-click the app → Open → Open** the first
> time (you only need to do this once). Notarized releases open normally.

Your data is stored in `~/Library/Application Support/TempSensor`.

## Linux

1. Download **`TempSensor-linux-x64-<version>.tar.gz`**.
2. Extract it and run the launcher:
   ```bash
   tar -xzf TempSensor-linux-x64-<version>.tar.gz
   ./temperature-hub/temperature-hub
   ```
3. Open <http://localhost:8088> if it doesn't open on its own.

Your data is stored in `~/.local/share/TempSensor` (override with the `DATA_DIR`
environment variable).

To run it automatically on boot, install it as a **systemd service** — see
[`../packaging/README.md`](../packaging/README.md).

---

## After it's running

- The dashboard is at **<http://localhost:8088>**. To reach it from your phone or
  another computer, use the hub computer's IP address, e.g. `http://192.168.1.50:8088`.
- Add a probe: power it on, and follow **Help → Get a probe online** in the app.
- No hardware yet? Click **Load demo data** on the dashboard to explore first.

## Updating

Download the newer installer and run it (Windows/macOS) or extract over the old
folder (Linux). Your settings and readings are kept — they live in the per-user
data directory listed above, not inside the app.

## Uninstalling

- **Windows:** Settings → Apps → TempSensor → Uninstall.
- **macOS:** drag TempSensor from Applications to the Trash.
- **Linux:** delete the extracted folder.

Your data directory is left in place so you don't lose readings by accident;
delete it manually if you want a clean slate.
