# ThermaProbe — Manufacturing QC Checklist

Pass/fail gate for **one** ThermaProbe unit before it is labeled and boxed.
Every line must be **PASS**. Any **FAIL** stops the unit — fix and re-run from
the failed step. This checklist is driven by
[`firmware/factory_flash.py`](../firmware/factory_flash.py), which flashes the
unit, reads its MAC, and prints the exact label identity + a matching QC list to
tick on the bench.

- Firmware: v2.0.0, protocol v1. Identity rules are defined in
  [`firmware/src/protocol.h`](../firmware/src/protocol.h) (single source of truth).
- One row of the **serial log CSV** (see [LABEL_TEMPLATE.md](LABEL_TEMPLATE.md))
  is filled per unit as you work, so every shipped unit is traceable.

---

## Bench setup (once per batch)

You need this available before running units:

- [ ] Flashing PC with PlatformIO (`pip install platformio`) and esptool
      (`pip install esptool`).
- [ ] USB-C data cable + the unit's USB power path known-good.
- [ ] A **bench ThermaHub** running on the LAN (`Start.sh` / `Start.bat`,
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
- [ ] **1.1** `pio run -t upload` completes with **SUCCESS** (0 errors).
      (`factory_flash.py` runs this; use `--no-flash` only to re-QC a flashed unit.)
- [ ] **1.2** Unit reboots on its own after flashing (no reset-loop on serial).

### 2. Identity — unique `ThermaProbe-<HEX6>`
- [ ] **2.1** esptool `read_mac` returns a MAC; `factory_flash.py` prints
      `Probe ID`, `Hostname`, `Setup Wi-Fi`, `Setup pass`.
- [ ] **2.2** Boot serial log prints the **same** `probe_id` the label shows
      (`ThermaProbe-` + UPPERCASE hex of the last 3 MAC bytes, 6 chars).
- [ ] **2.3** `GET http://<probe-ip>/whoami` (or `thermaprobe-<hex6>.local`)
      returns `{id,name,fw,mac}` and `id` == the printed `probe_id`, `fw` ==
      `2.0.0`.
- [ ] **2.4** **Uniqueness:** the `probe_id` is not already present in the
      batch serial log CSV. (Two units can only collide on a duplicate MAC —
      quarantine both if it ever happens.)

### 3. SoftAP setup network
- [ ] **3.1** With no saved Wi-Fi, the unit brings up SoftAP SSID
      **`ThermaProbe-<HEX6>`** (== `probe_id`), visible on a phone.
- [ ] **3.2** The AP is **WPA2** (asks for a password, not open) and joins with
      the printed key **`TP-<8 UPPERCASE hex of last 4 MAC bytes>`**.
- [ ] **3.3** After joining the AP, `http://192.168.4.1` serves the captive
      setup page (Wi-Fi picker with SSID + password fields).

### 4. Joins test Wi-Fi
- [ ] **4.1** Enter the bench test SSID + password in the captive portal;
      unit stores creds and reconnects in STA mode.
- [ ] **4.2** Serial shows a successful join / an IP; `GET /status` reachable
      over the test LAN, `wifi_rssi` is non-zero and plausible (e.g. > -85 dBm).

### 5. Plausible temperature
- [ ] **5.1** `GET /status` shows `sensor_ok=true` and a non-null
      `temperature_c` within **-60..150 °C** and sane for the room
      (roughly ambient; not 85.0 power-on, not -127/NaN).
- [ ] **5.2** Warming the probe (fingers / breath) moves the reading in the
      right direction within a few sample intervals.

### 6. One successful ingest POST to the bench hub
- [ ] **6.1** Provision the unit against the bench hub (hub auto-provisioner,
      or `POST /provision {server_url,token,interval_ms}` — add
      `X-Provision-Secret` if this unit has one set, see step 7).
- [ ] **6.2** `GET /status` shows `last_post_ok=true` and `last_post_code=200`.
- [ ] **6.3** The unit appears in the bench hub's probe list
      (`GET /api/probes`) and a fresh row for this `probe_id` lands in
      `download/temperature_log.csv`
      (columns `timestamp,temperature_c,temperature_f,probe_id`).

### 7. Provision secret (optional lock-down)
- [ ] **7.1** If this batch ships **locked**, a per-unit `X-Provision-Secret`
      has been generated, written to NVS (`prov_secret`), and re-provision now
      **rejects** a wrong/absent secret (`accepted:false`). Record the secret on
      the label + serial log.
- [ ] **7.2** If shipping **open plug-and-play**, `prov_secret` is left empty
      and this is noted on the serial log (label secret field = `—`).

### 8. Label + record
- [ ] **8.1** Print and apply the unit label per
      [LABEL_TEMPLATE.md](LABEL_TEMPLATE.md); verify the printed `probe_id`,
      SoftAP name, WPA2 password, and (if set) provision secret match the unit.
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
| Duplicate `probe_id` (2.4) | Quarantine both units; escalate — indicates a cloned/duplicate MAC. |
