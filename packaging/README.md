# Packaging the Temperature Hub

Build a **self-contained folder** customers can run without installing Python.
Built with [PyInstaller](https://pyinstaller.org/).

> **One-click installers.** For end users, the [`release`](../.github/workflows/release.yml)
> workflow turns this bundle into a **Windows `.exe` installer**, a **macOS `.dmg`**,
> and a **Linux `.tar.gz`**, attached to a GitHub Release — see
> [`../docs/INSTALL.md`](../docs/INSTALL.md) (users) and
> [`../docs/RELEASE_SIGNING.md`](../docs/RELEASE_SIGNING.md) (how to sign/notarize
> them). The rest of this file covers the raw bundle + service install.

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
When frozen, the hub keeps `config.json`, `temperature_log.db`, and `logs/` in a
**per-user, writable directory** so a copy installed in a read-only location
(Program Files, `/Applications`) works without admin rights:

| OS | Default data directory |
| --- | --- |
| Windows | `%LOCALAPPDATA%\Setpoint` |
| macOS | `~/Library/Application Support/Setpoint` |
| Linux | `~/.local/share/Setpoint` (or `$XDG_DATA_HOME/Setpoint`) |

Override with the `DATA_DIR` environment variable (recommended for service
installs — point it at a dedicated writable directory). For backward
compatibility, a "portable" bundle that already has a `config.json`/
`temperature_log.db` **next to the executable** keeps using that folder. The
bundled `config.example.json` seeds `config.json` on first run.

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

### Windows (start at boot, before anyone signs in)

> ⚠️ **Read this first — it is how data gets "lost".** The hub keeps its data in
> `%LOCALAPPDATA%\Setpoint` **of the account it runs as**. A service runs as a
> different account (LocalSystem) by default, whose `%LOCALAPPDATA%` is somewhere
> else entirely — so the hub starts as a brand-new install: empty history, a new
> device token, and every provisioned probe rejected with 401 until it is
> re-provisioned. Either run it as **your own account** (Option A), or point
> `DATA_DIR` at the existing folder (Option B).

**Option A — Task Scheduler, as your own account (no extra tools; recommended).**
Task Scheduler → **Create Task** (not "Basic Task"):

- **General:** *Run whether user is logged on or not*; *Run with highest privileges*;
  the user is **your** account (so `%LOCALAPPDATA%\Setpoint` is the same folder).
- **Triggers:** *At startup*, *Delay task for* 1 minute (lets the network come up).
- **Actions:** *Start a program* → `%LOCALAPPDATA%\Programs\Setpoint\temperature-hub.exe`
  (the per-user install location; `C:\Program Files\Setpoint\` for an all-users install).
- **Settings:** **untick** *Stop the task if it runs longer than 3 days* — it is
  ticked by default and would stop the hub every three days. Tick *If the task
  fails, restart every* 1 minute, up to 999 times.
- Then remove the installer's sign-in shortcut (`shell:startup` → *Setpoint*), or
  leave it: a second launch only opens the running hub's dashboard.

**Option B — a real service with [NSSM](https://nssm.cc/).** Set `DATA_DIR`
explicitly so the service account uses your existing data:
```bat
nssm install Setpoint "C:\Program Files\Setpoint\temperature-hub.exe"
nssm set Setpoint AppDirectory "C:\Program Files\Setpoint"
nssm set Setpoint AppEnvironmentExtra DATA_DIR=C:\ProgramData\Setpoint OPEN_BROWSER=0
nssm set Setpoint Start SERVICE_AUTO_START
nssm start Setpoint
```
Before the first start, **move** `%LOCALAPPDATA%\Setpoint\*` into
`C:\ProgramData\Setpoint\` (stop the desktop copy first) — that carries over the
history, settings and device token, so probes keep posting.

**Either way:** allow `temperature-hub.exe` through Windows Firewall on **Private**
networks (an all-users install adds that rule itself), and set the BIOS/UEFI option
*Restore on AC power loss* to **Power On** so the PC comes back after a power cut.

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
