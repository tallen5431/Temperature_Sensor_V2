# ThermaProbe Firmware

Reference ESP32 firmware for the **ThermaProbe** — the wireless temperature
probe that feeds the local-first **ThermaHub** appliance. This is the actual
image that gets flashed onto manufactured units. It implements the *probe side*
of ThermaHub protocol **v1**.

- **MCU:** ESP32-WROOM-32E (`esp32dev`)
- **Framework:** Arduino via [PlatformIO](https://platformio.org/)
- **Firmware version:** 2.0.0 · **Protocol:** 1
- **Sensor:** DS18B20 (default) or MAX31855 K-type thermocouple (build option)

All GPIO/pin assignments live in [`src/protocol.h`](src/protocol.h), which is
the single source of truth shared with the hardware docs
(`docs/BOM.md`, `docs/ASSEMBLY.md`) so firmware and hardware cannot drift.

---

## 1. Install PlatformIO

Either the VS Code extension, or the CLI:

```bash
pip install platformio
```

## 2. Wire the sensor

See **`docs/ASSEMBLY.md`** (wiring, enclosure) and **`docs/BOM.md`** (parts).
Summary, matching `src/protocol.h`:

**DS18B20 (default)**

| DS18B20 | ESP32 |
|---------|-------|
| VDD (red)    | 3V3 |
| GND (black)  | GND |
| DATA (yellow)| GPIO4 (`ONE_WIRE_BUS`) |

Add a **4.7 kΩ pull-up** from DATA to 3V3 (required for 1-Wire).

**MAX31855 thermocouple (optional)** — CS=GPIO5, SCK=GPIO18, SO(MISO)=GPIO19.

Status LED: GPIO2 (on-board LED on most dev boards).

## 3. Select the sensor back-end

In [`platformio.ini`](platformio.ini) `build_flags`:

- `-D SENSOR_DS18B20` — default, 1-Wire DS18B20.
- `-D SENSOR_MAX31855` — thermocouple. Also uncomment the `adafruit/Adafruit
  MAX31855 library` line in `lib_deps`.

## 4. Build & flash

```bash
pio run                 # compile
pio run -t upload       # flash over USB
pio device monitor      # serial console @ 115200 baud
```

Or use the guided factory helper (flash + compute the unit label + QC prompts):

```bash
python factory_flash.py                # flash, then print label + QC checklist
python factory_flash.py --no-flash     # just read MAC and print the label
python factory_flash.py --port COM5    # pin a serial port
```

## 5. First-run setup (SoftAP)

With no saved Wi-Fi, the probe starts a **WPA2 SoftAP** named
`ThermaProbe-<HEX6>` (password on the unit label). Join it with a phone/laptop,
let the captive portal open (or browse to `http://192.168.4.1`), enter your home
Wi-Fi SSID + password, and Save. The probe stores the creds to NVS, reboots, and
joins your network. It then appears **automatically** in ThermaHub — the hub
discovers it over mDNS and pushes the ingest URL + token to it.

---

## Identity (must match hub + label)

Derived once at boot from the ESP32 efuse MAC:

```
HEX6        = UPPERCASE hex of the last 3 MAC bytes      e.g. 9A3F2C
probe_id    = "ThermaProbe-" + HEX6                      e.g. ThermaProbe-9A3F2C
hostname    = "thermaprobe-" + lowercase(HEX6)           -> thermaprobe-9a3f2c.local
SoftAP SSID = probe_id
AP password = "TP-" + UPPERCASE hex of last 4 MAC bytes  e.g. TP-289A3F2C
```

`factory_flash.py` computes the identical strings from esptool's `read_mac`, so
the printed label always matches the running firmware. The same `probe_id` is
sent as the mDNS TXT `id`, the HTTP `X-Probe-ID` header, and the JSON `probe_id`
body field — the firmware asserts/logs this invariant at boot.

## mDNS advertisement

Service `_temps-probe._tcp.local.` on TCP port 80, TXT records:

| key | value |
|-----|-------|
| `id`    | `<probe_id>` (equals `X-Probe-ID`) |
| `name`  | friendly name, or `<probe_id>` |
| `fw`    | `2.0.0` |
| `proto` | `1` |

## HTTP endpoints (port 80)

| Method / path | Purpose |
|---------------|---------|
| `POST /provision` | Body `{server_url, token, interval_ms}`. Requires header `X-Provision-Secret` **only when the unit has a secret stored** (see note below). Persists settings to NVS. Returns `{id,name,fw,accepted:true}`. |
| `GET /whoami`  | `{id,name,fw,mac}` |
| `GET /status`  | `{id,wifi_rssi,uptime_s,last_post_ok,last_post_code,server_url,temperature_c,sensor_ok}` |
| `GET /` (SoftAP) | Wi-Fi setup page; `POST /save` stores creds and reboots. |

**Provision secret note:** the spec defines a per-unit `X-Provision-Secret`
(from the label/QR) that gates `/provision`. To preserve ThermaHub's zero-touch
auto-provisioning (the shipped hub pushes the ingest URL/token with no secret
header), this firmware enforces the secret **only when one is stored in NVS**
(`prov_secret`). Out of the box that field is empty, so the hub can provision on
a trusted LAN; a field tech can write a `prov_secret` to lock a unit down.

## Ingest (probe → hub)

Every `interval_ms` the probe reads the sensor and, if the reading is valid,
POSTs to the provisioned `server_url` (`http://<hub>:8080/api/ingest`):

```
POST /api/ingest
X-Probe-ID: ThermaProbe-9A3F2C
X-Token: <token pushed by the hub>
Content-Type: application/json

{"temperature_c": 4.31, "probe_id": "ThermaProbe-9A3F2C", "timestamp": "uptime+123s"}
```

The hub validates the value is finite and within −60…150 °C and stamps the
authoritative timestamp. Post result is tracked in `/status`
(`last_post_ok`, `last_post_code`).

## Sensor fault handling

Fault codes are rejected and **no** post is sent for that cycle
(`sensor_ok=false`): DS18B20 `85.0` (power-on reset), `-127` (disconnected),
`NaN`, and anything outside −60…150 °C. MAX31855 open/short → `NaN` → rejected.

## Files

| File | Purpose |
|------|---------|
| `platformio.ini` | Board/framework, pinned libs, sensor build flag. |
| `src/protocol.h` | Version, pins, SoftAP/mDNS constants, identity rules. |
| `src/main.cpp`   | Full firmware implementation. |
| `factory_flash.py` | Flash + label + QC helper. |
