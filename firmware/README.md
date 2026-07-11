# TempSensor Firmware

Reference ESP32 firmware for the **TempSensor** — the wireless, battery-powered
temperature probe that feeds the local-first **TempSensor** appliance. This is the
actual image flashed onto manufactured units. It implements the *probe side* of
TempSensor protocol **v1**.

The canonical, shipping firmware is the Arduino sketch
[`../esp32_temp_probe/esp32_temp_probe.ino`](../esp32_temp_probe/esp32_temp_probe.ino)
— the **deep-sleep battery firmware** (WiFiManager captive-portal setup, LittleFS
offline buffer, NTP time). The former PlatformIO project (`platformio.ini` +
`src/main.cpp`) has been removed; only the sketch is built now.

- **MCU:** ESP32-WROOM-32E
- **Toolchain:** Arduino (Arduino IDE or `arduino-cli`) — **not** PlatformIO
- **Firmware version:** 2.4.0 · **Protocol:** 1
- **Sensor:** DS18B20 (1-Wire) — the **only** sensor in the current firmware
- **Power:** rechargeable-lithium battery; deep-sleeps between readings for long
  battery life

Pin assignments and the identity contract live in
[`src/protocol.h`](src/protocol.h), the single source of truth shared with the
hardware docs (`docs/BOM.md`, `docs/ASSEMBLY.md`) so firmware and hardware cannot
drift.

---

## 1. Toolchain & libraries

Install the Arduino ESP32 core and the sketch's libraries. With `arduino-cli`:

```bash
arduino-cli core update-index
arduino-cli core install esp32:esp32
arduino-cli lib install WiFiManager ArduinoJson OneWire DallasTemperature
```

Libraries used by the sketch:

- **WiFiManager** (by tzapu) — captive-portal Wi-Fi setup
- **ArduinoJson** (v6 or v7) — ingest + API JSON
- **OneWire** + **DallasTemperature** — DS18B20
- **ESPmDNS**, **LittleFS**, **Preferences** (NVS) — bundled with the ESP32 core
- Core headers: `WiFi`, `HTTPClient`, `WebServer`, `time.h`, `esp_sleep`, `esp_random`

Recommended partition scheme (Arduino IDE → Tools → Partition Scheme, or an
`arduino-cli` board option): **"No OTA (2MB APP/2MB SPIFFS)"** — the ~2 MB
LittleFS backs the offline buffer (~38 000 readings).

## 2. Wire the sensor

See **`docs/ASSEMBLY.md`** (wiring, battery, enclosure) and **`docs/BOM.md`**
(parts). Summary, matching `src/protocol.h`:

**DS18B20 (the only supported sensor)**

| DS18B20 | ESP32 |
|---------|-------|
| VDD (red)    | 3V3 |
| GND (black)  | GND |
| DATA (yellow)| **GPIO5** (`ONE_WIRE_BUS`) |

Add a **4.7 kΩ pull-up** from DATA to 3V3 (required for 1-Wire).

Status LED: **GPIO2** (`LED_BUILTIN` / on-board LED on most dev boards).

> MAX31855 thermocouple and SHT4x temp+humidity pin maps exist in `protocol.h`
> but are **future/optional and not implemented in the current firmware** — the
> shipping build is DS18B20-only. Do not populate them on production units.

## 3. Build & flash

With `arduino-cli` (run from the sketch directory `esp32_temp_probe/`):

```bash
arduino-cli compile --fqbn esp32:esp32:esp32 .
arduino-cli upload -p <PORT> --fqbn esp32:esp32:esp32 .
arduino-cli monitor -p <PORT> -c baudrate=115200      # serial console
```

Or open `esp32_temp_probe/esp32_temp_probe.ino` in the **Arduino IDE**, select
the ESP32 board + the "No OTA (2MB APP/2MB SPIFFS)" partition scheme, and upload.

Or use the guided factory helper (flash + capture the unit label + QC prompts):

```bash
python factory_flash.py                      # flash, then print label + QC checklist
python factory_flash.py --no-flash           # already-flashed unit: capture label + QC
python factory_flash.py --port /dev/ttyUSB0  # pin a serial port
```

`factory_flash.py` invokes `arduino-cli compile`/`upload` and reads the unit's
identity from the boot serial `[label]` line (see **Identity** below).

## 4. First-run setup (SoftAP)

With no saved Wi-Fi, the probe starts an **open SoftAP** (no password) whose SSID
**is the probe id** (e.g. `TempSensor-9A3F2C`). Join it with a phone/laptop, let
the WiFiManager captive portal open (or browse to `http://192.168.4.1`), and enter:

- your home Wi-Fi SSID + password (required), and
- optionally the server URL / ingest token / read interval.

The probe stores the credentials to NVS and joins your network. It then appears
**automatically** in TempSensor — the hub discovers it over mDNS and pushes the
ingest URL + token via `POST /provision`. On a later deep-sleep wake the probe
fast-reconnects to the saved network **without** re-opening the portal.

---

## Identity (must match hub + label)

Derived **once** at first boot and **persisted in NVS** for the life of the unit
(a later failed sensor read can no longer flip it):

```
HEX6        = UPPERCASE hex of the LAST 6 hex (3 bytes) of the DS18B20 sensor
              ROM code; if no sensor is present, the last 6 hex of the ESP32
              efuse MAC (chip id).                         e.g. 9A3F2C
probe_id    = "TempSensor-" + HEX6                        e.g. TempSensor-9A3F2C
mDNS host   = probe_id  ->  <probe_id>.local              -> TempSensor-9A3F2C.local
SoftAP SSID = probe_id
SoftAP      = open (no password); only up during first-time setup
```

At every boot the firmware prints a machine-readable line that `factory_flash.py`
parses for the label:

```
[label] probe_id=TempSensor-9A3F2C ap_ssid=TempSensor-9A3F2C ap_pass=none
```

The same `probe_id` is sent as the mDNS TXT `id`, the HTTP `X-Probe-ID` header,
and the JSON `probe_id` body field on every ingest POST.

## mDNS advertisement

Service `_temps-probe._tcp.local.` on TCP port 80, TXT records:

| key | value |
|-----|-------|
| `id`   | `<probe_id>` (equals `X-Probe-ID`) |
| `name` | `<probe_id>` |

## HTTP endpoints (port 80)

| Method / path | Purpose |
|---------------|---------|
| `GET /` | HTML status page (auto-refreshing): current temp, id, interval, sleep mode, buffered rows. |
| `GET /whoami` | `{id, name, mac, ds18b20_rom, fw_version, interval_ms, server_url, time_valid}` |
| `GET /status` | `{id, interval_ms, server_url, time_valid, last_c, last_ms, last_ts, buffered_bytes, buffered_est_rows, fs_total_kb, fs_free_kb, sleep_mode, wake_count}` |
| `POST /provision` | Body `{server_url, token, interval_ms}`; persists to NVS. Returns `{ok:true, server_url, interval_ms}`. (`OPTIONS` returns 204 for CORS.) |

Wi-Fi credential entry is handled by the WiFiManager captive portal during
setup, not by a custom endpoint.

> **No provision secret in the current firmware:** `POST /provision` is accepted
> on the trusted LAN with no `X-Provision-Secret` gate, which is what keeps
> TempSensor's zero-touch auto-provisioning working. A per-unit provision secret
> is a possible future hardening, not a shipped feature.

## Reachability & deep sleep

- When the configured interval is **≥ ~10 s** the probe **deep-sleeps** between
  readings (idle current <1 mA). After each wake it keeps the HTTP server alive
  for a short window (~3 s) so the hub's auto-provision request / a browser visit
  can reach it, then sleeps again.
- When the interval is **< ~10 s** the probe stays **always-on** with WiFi modem
  sleep; the web server and mDNS are then continuously reachable.

## Ingest (probe → hub)

Every `interval_ms` the probe reads the DS18B20 and POSTs to the provisioned
`server_url` (the hub's ingest endpoint, e.g. `http://<hub>:8080/api/ingest`):

```
POST /api/ingest
X-Probe-ID: TempSensor-9A3F2C
X-Token: <token pushed by the hub, if set>
Content-Type: application/json

{"timestamp":"2026-07-11T14:03:00Z","temperature_c":4.31,"temperature_f":39.76,"probe_id":"TempSensor-9A3F2C"}
```

If the POST fails or the network is down, the reading is appended to the LittleFS
offline buffer (`/buf.csv`) with its timestamp and flushed (in order, resumable
via a persisted byte offset) once the hub is reachable again.

The hub stores telemetry in its CSV with columns
`timestamp,temperature_c,temperature_f,probe_id,humidity_pct,vpd_kpa`. A DS18B20
probe fills the first four; `humidity_pct` and `vpd_kpa` stay empty (they are
populated only by a humidity-capable probe, which the current firmware is not).

## Sensor fault handling

A DS18B20 disconnect (`DEVICE_DISCONNECTED_C` / `-127`) is detected: the bus is
re-initialised and **no** reading is posted or buffered for that cycle. In
deep-sleep mode the unit still sleeps and retries the sensor on the next wake.
The `GET /` page and `/whoami` surface the DS18B20 ROM and last reading for
diagnosis.

## Files

| File | Purpose |
|------|---------|
| `../esp32_temp_probe/esp32_temp_probe.ino` | **Canonical firmware** (deep-sleep battery firmware). |
| `src/protocol.h` | Version, pins, SoftAP/mDNS constants, identity rules (contract the sketch follows). |
| `factory_flash.py` | Flash (arduino-cli) + capture label + QC helper. |
