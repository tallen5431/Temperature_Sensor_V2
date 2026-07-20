**Setpoint hub** — the self-hosted dashboard for your Setpoint Wi-Fi temperature probes.

Download the installer for your system from the **Assets** below, then follow
[INSTALL.md](https://github.com/tallen5431/Temperature_Sensor_V2/blob/main/docs/INSTALL.md).
The dashboard opens in your browser at <http://localhost:8088>.

### ⚠️ First launch shows a security prompt — this is expected

These installers aren't code-signed yet, so your OS warns the first time. It's safe to proceed:

- **Windows:** *"Windows protected your PC"* → **More info → Run anyway**
- **macOS:** *"can't be opened because Apple cannot check it"* → **right-click the app → Open → Open** (once only)
- **Linux:** no prompt — extract the tarball and run `./temperature-hub/temperature-hub`

| System | File |
| --- | --- |
| Windows | `Setpoint-Setup-<version>.exe` |
| macOS | `Setpoint-<version>.dmg` |
| Linux | `Setpoint-linux-x64-<version>.tar.gz` |

_Your settings and readings live in a per-user data directory (see INSTALL.md), so updating is just running the newer installer._
