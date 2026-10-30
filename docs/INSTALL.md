# Installing the Setpoint hub

The hub is the small app that collects readings from your probes and shows the
dashboard. Install it on any always-on computer (a laptop, a mini-PC, a Raspberry
Pi) on the same network as your probes. You do **not** need to install Python.

Download the installer for your system from the
[**Releases**](https://github.com/tallen5431/Temperature_Sensor_V2/releases)
page, then follow the steps below. When it starts, the dashboard opens in your
browser automatically at <http://localhost:8088>.

---

## Windows

1. Download **`Setpoint-Setup-<version>.exe`**.
2. Double-click it and follow the installer. It installs just for you (no admin
   password needed) and offers to add a desktop shortcut and to start
   automatically when you sign in. **Leave that second box ticked** — a hub
   that isn't running after a restart can't alert you.
3. Launch **Setpoint** from the Start menu (or the desktop). The dashboard
   opens in your browser. If **Windows Firewall** asks, tick **Private
   networks** and click **Allow** — that is how your probes reach the hub.
   (Choosing *Install for all users* in the installer adds this rule for you.)
   Clicking the icon again later just opens the dashboard of the hub that is
   already running.

> **Should it survive a power cut with nobody around?** Out of the box it starts
> when you sign in. To start it at boot before anyone signs in, and to have the
> PC switch itself back on after a power cut, follow
> [`../packaging/README.md`](../packaging/README.md#windows-start-at-boot-before-anyone-signs-in).

> **"Windows protected your PC" (SmartScreen)?** This appears for apps that
> aren't signed with a paid certificate. Click **More info → Run anyway**. (Signed
> releases won't show this.)

Your data (settings, readings, logs) is stored in
`%LOCALAPPDATA%\Setpoint`.

## macOS

1. Download **`Setpoint-<version>.dmg`**.
2. Open the `.dmg` and drag **Setpoint** to your Applications folder.
3. Launch **Setpoint**. The dashboard opens in your browser.

> **"Setpoint can't be opened because Apple cannot check it…"?** This appears
> for apps that aren't notarized. **Right-click the app → Open → Open** the first
> time (you only need to do this once). Notarized releases open normally.

Your data is stored in `~/Library/Application Support/Setpoint`.

## Linux

1. Download **`Setpoint-linux-x64-<version>.tar.gz`**.
2. Extract it and run the launcher:
   ```bash
   tar -xzf Setpoint-linux-x64-<version>.tar.gz
   ./temperature-hub/temperature-hub
   ```
3. Open <http://localhost:8088> if it doesn't open on its own.

Your data is stored in `~/.local/share/Setpoint` (override with the `DATA_DIR`
environment variable).

To run it automatically on boot, install it as a **systemd service** — see
[`../packaging/README.md`](../packaging/README.md).

---

## After it's running

- The dashboard is at **<http://localhost:8088>**. To reach it from your phone or
  another computer, use the hub computer's IP address, e.g. `http://192.168.1.50:8088`.
- Add a probe: power it on, and follow **Help → Get a probe online** in the app.
- No hardware yet? Click **Load demo data** on the dashboard to explore first.
- **Before you rely on it**, open **Settings → Reliability & access**: turn on the
  outside check-in (so you hear if this PC stops), and a login if anyone else uses
  this network. Setpoint already keeps Windows and macOS from idling to sleep
  while it runs. On a **Linux desktop** that suspends, run
  `sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target`.
  Details: [User manual §12](USER_MANUAL.md#12-make-it-safe-to-walk-away).
- **Alerts on your phone, and viewing the dashboard away from home:**
  [User manual §11 and §13](USER_MANUAL.md#11-get-alerts-on-your-phone).

## Updating

Download the newer installer and run it (Windows/macOS) or extract over the old
folder (Linux). Your settings and readings are kept — they live in the per-user
data directory listed above, not inside the app.

## Uninstalling

- **Windows:** Settings → Apps → Setpoint → Uninstall.
- **macOS:** drag Setpoint from Applications to the Trash.
- **Linux:** delete the extracted folder.

Your data directory is left in place so you don't lose readings by accident;
delete it manually if you want a clean slate.
