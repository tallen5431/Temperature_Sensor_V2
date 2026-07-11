# TempSensor — Manufacturing QC Checklist

Pass/fail gate for **one** TempSensor unit before it is labeled and boxed.
Every line must be **PASS**. Any **FAIL** stops the unit — fix and re-run from
the failed step. This checklist is driven by
[`firmware/factory_flash.py`](../firmware/factory_flash.py), which flashes the
sketch with `arduino-cli`, captures the unit's identity from the boot `[label]`
serial line, and prints the exact label + a matching QC list to tick on the bench.

- Firmware: **v2.4.0**, protocol v1. Identity rules and pin map are defined in
  [`firmware/src/protocol.h`](../firmware/src/protocol.h) (single source of truth);
  the shipping firmware is the sketch
  [`esp32_temp_probe/esp32_temp_probe.ino`](../esp32_temp_probe/esp32_temp_probe.ino).
- One row of the **serial log CSV** (see [LABEL_TEMPLATE.md](LABEL_TEMPLATE.md))
  is filled per unit as you work, so every shipped unit is traceable.

---

## Bench setup (once per batch)

You need this available before running units:

- [ ] Flashing PC with **arduino-cli** (or the Arduino IDE) plus the ESP32 core
      and libraries installed:
      `arduino-cli core install esp32:esp32` and
      `arduino-cli lib install WiFiManager ArduinoJson OneWire DallasTemperature`.
      (Optional: `esptool` only if you want to log the chip MAC.)
- [ ] USB-C data cable + the unit's USB power path known-good.
- [ ] A charged **rechargeable-lithium battery** fitted (or the unit on USB) so
      deep-sleep wake behaviour can be observed.
- [ ] A **bench TempSensor** running on the LAN (`Start.sh` / `Start.bat`,
      dashboard at `http://localhost:8080`). Note its LAN URL and device token —
      you will confirm one live ingest into it.
- [ ] A phone or laptop that can see 2.4 GHz Wi-Fi (to verify the SoftAP).
- [ ] A test 2.4 GHz Wi-Fi network the probe can join (SSID + password).
- [ ] Label stock + printer, and the per-batch QR to the setup page.

---

## Per-unit QC steps

Run `python firmware/factory_flash.py --port <PORT>` and follow its prompts;
tick each item below as the operator confirms it.

### 1. Flash
- [ ] **1.1** `arduino-cli compile` **and** `arduino-cli upload` complete with
      **SUCCESS** (0 errors). (`factory_flash.py` runs both; use `--no-flash`
      only to re-QC an already-flashed unit.)
- [ ] **1.2** Unit reboots on its own after flashing (no reset-loop on serial).

### 2. Identity — persistent `TempSensor-<HEX6>`
- [ ] **2.1** Boot serial prints the machine-readable line
      `[label] probe_id=... ap_ssid=... ap_pass=...`; `factory_flash.py` echoes
      `Probe ID`, `Setup Wi-Fi`, `Setup pass`.
- [ ] **2.2** `probe_id` is `TempSensor-<HEX6>` (6 UPPERCASE hex, derived from
      the DS18B20 sensor ROM and **persisted in NVS**). Confirm it is stable
      across a power-cycle — it must **not** change between boots.
- [ ] **2.3** `GET http://<probe-ip>/whoami` (or `TempSensor-<HEX6>.local`)
      returns `{id,name,mac,ds18b20_rom,fw_version,...}` with `id` == the printed
      `probe_id` and `fw_version` == **`2.4.0`**.
- [ ] **2.4** **Uniqueness:** the `probe_id` is not already present in the batch
      serial log CSV. (A collision means a duplicate DS18B20 ROM or MAC-fallback
      chip — quarantine both if it ever happens.)

### 3. SoftAP setup network (per-unit WPA2)
- [ ] **3.1** With no saved Wi-Fi, the unit brings up SoftAP SSID
      **`TempSensor-<HEX6>`** (== `probe_id`), visible on a phone.
- [ ] **3.2** The AP is **WPA2** (asks for a password, not open) and joins with
      the **per-unit random** key from the serial `[label]` line, `ap_pass` =
      `TS-<16 hex>` (19 chars) — record it on the unit label.
- [ ] **3.3** After joining the AP, `http://192.168.4.1` serves the WiFiManager
      captive setup page (home-Wi-Fi picker + optional server/token/interval fields).

### 4. Joins test Wi-Fi
- [ ] **4.1** Enter the bench test SSID + password in the captive portal;
      unit stores creds and reconnects in STA mode.
- [ ] **4.2** Serial shows a successful join / an IP; `GET /status` is reachable
      over the test LAN and `time_valid` becomes `true` after NTP sync.

### 5. Plausible temperature
- [ ] **5.1** `GET /status` shows a non-null `last_c` within **-60..150 °C** and
      sane for the room (roughly ambient; not 85.0 power-on, not -127/NaN). The
      `GET /` page shows the same reading in °C/°F.
- [ ] **5.2** Warming the probe (fingers / breath) moves the reading in the
      right direction within a few sample intervals.

### 6. One successful ingest to the bench hub
- [ ] **6.1** Provision the unit against the bench hub (hub auto-provisioner,
      or `POST /provision {server_url,token,interval_ms}`; returns `{ok:true}`).
      *(The current firmware has no provision-secret gate — see step 7.)*
- [ ] **6.2** A fresh row for this `probe_id` lands in the hub telemetry CSV
      (`download/temperature_log.csv`, columns
      `timestamp,temperature_c,temperature_f,probe_id,humidity_pct,vpd_kpa` —
      `humidity_pct`/`vpd_kpa` are blank for a DS18B20 probe).
- [ ] **6.3** The unit appears in the bench hub's probe list
      (`GET /api/probes`) / on the dashboard at `http://localhost:8080`.

### 7. Provision security (informational)
- [ ] **7.1** Note on the serial log that this firmware ships **open
      plug-and-play**: `POST /provision` is accepted on the trusted LAN with **no**
      `X-Provision-Secret` gate (a per-unit provision secret is a future option,
      not implemented in v2.4.0). The setup network is instead protected by the
      per-unit **WPA2** SoftAP key (step 3.2).

### 8. Label + record
- [ ] **8.1** Print and apply the unit label per
      [LABEL_TEMPLATE.md](LABEL_TEMPLATE.md); verify the printed `probe_id`,
      SoftAP name, and WPA2 password match the `[label]` serial line.
- [ ] **8.2** Scan the label QR — it opens the setup page.
- [ ] **8.3** Fill this unit's row in the batch **serial log CSV**
      (see LABEL_TEMPLATE.md for the column spec) and mark overall
      **PASS / FAIL** with operator initials + date.

---

## Disposition

| Result | Action |
|--------|--------|
| All steps PASS | Box the unit; keep the serial-log row. |
| Any step FAIL | Do **not** ship. Note the failing step number in the serial log, fix, re-run from that step. |
| Duplicate `probe_id` (2.4) | Quarantine both units; escalate — indicates a duplicate DS18B20 ROM or MAC-fallback chip. |
