# ThermaProbe — Unit Label Template

What goes on the physical label applied to every ThermaProbe during QC
(step 8 of [QC_CHECKLIST.md](QC_CHECKLIST.md)). All identity values are computed
by [`firmware/factory_flash.py`](../firmware/factory_flash.py) from the ESP32
MAC and must match what the firmware derives at boot
([`firmware/src/protocol.h`](../firmware/src/protocol.h) is the source of truth).

The label is the customer's only reference for setup, so it MUST be correct and
legible. A non-technical buyer uses it to (a) find the setup Wi-Fi, (b) type the
Wi-Fi password, and (c) scan a QR to the setup page.

---

## Fields on each label

| # | Field | Value / format | Source |
|---|-------|----------------|--------|
| 1 | **Probe ID** (human-readable) | `ThermaProbe-<HEX6>` — UPPERCASE hex of the last 3 MAC bytes, e.g. `ThermaProbe-9A3F2C` | `factory_flash.py` `Probe ID` |
| 2 | **Setup Wi-Fi (SSID)** | `ThermaProbe-<HEX6>` (same string as Probe ID); WPA2 | `factory_flash.py` `Setup Wi-Fi` |
| 3 | **Setup Wi-Fi password** | `TP-<HEX8>` — `TP-` + UPPERCASE hex of the last 4 MAC bytes, e.g. `TP-289A3F2C` (11-char WPA2 key) | `factory_flash.py` `Setup pass` |
| 4 | **Provision secret** (`X-Provision-Secret`) | Per-unit secret gating `POST /provision`. Print only if the unit is locked (secret written to NVS `prov_secret`); otherwise print `—` | maker-generated per unit |
| 5 | **Setup QR** | QR encoding the setup page URL (see below) | printed |
| 6 | **Hostname** (optional, small print) | `thermaprobe-<hex6>.local` (lowercase) | `factory_flash.py` `Hostname` |

Notes:
- Fields 1–3 and 6 are all derived from the same MAC, so they always agree.
  Do **not** hand-edit one without the others.
- The **provision secret** is a security field: keep it on the customer's copy
  (they need it to re-provision a locked unit) but treat it like a password —
  never reuse one secret across units.
- The **setup QR** should point at the customer setup entry point, e.g.
  `http://192.168.4.1` (the captive portal, reachable once the phone joins the
  probe's SoftAP), or your hosted setup-help page for this product. Keep it
  consistent across a batch.

---

## Printable label layout sketch

Small 2-up thermal/laser label, roughly 50 × 25 mm. Adjust to your stock.

```
+------------------------------------------------------+
|  ThermaHub  •  ThermaProbe            [ ##### ]       |
|                                       [ #QR# ]  <- scan to set up
|  ID:   ThermaProbe-9A3F2C             [ ##### ]       |
|                                                      |
|  Setup Wi-Fi : ThermaProbe-9A3F2C   (WPA2)           |
|  Wi-Fi pass  : TP-289A3F2C                           |
|  Provision   : <secret or  —  if open>               |
|  host: thermaprobe-9a3f2c.local                      |
+------------------------------------------------------+
   fw 2.0.0 / proto 1        S/N: __________  QC:____
```

- Top-right: the setup **QR** (field 5).
- Big, unambiguous type for the Wi-Fi SSID + password (fields 2–3) — this is
  what a non-technical buyer squints at.
- `S/N` and `QC` blanks are hand-filled at boxing (serial + operator initials)
  and mirror the serial-log CSV row.
- If shipping open plug-and-play, print `Provision: —` so the customer knows no
  secret is required.

---

## Serial-log CSV column spec (one row per unit)

The maker fills **one row per unit** during QC and keeps the file as the batch
build/traceability record. This is a manufacturing log — it is **separate** from
the hub's telemetry `download/temperature_log.csv`
(`timestamp,temperature_c,temperature_f,probe_id`); do not conflate them.

Header row:

```
serial,build_date,operator,mac,probe_id,hostname,ap_ssid,ap_password,provision_secret,fw_version,test_wifi_ssid,temperature_c,ingest_ok,qc_result,notes
```

| Column | Meaning | Example |
|--------|---------|---------|
| `serial` | Your batch serial / sequence for the unit | `TP2607-001` |
| `build_date` | Date built (ISO) | `2026-07-06` |
| `operator` | Who ran QC (initials) | `TJ` |
| `mac` | Full chip MAC from esptool | `A4:CF:12:9A:3F:2C` |
| `probe_id` | `ThermaProbe-<HEX6>` (must be unique in file) | `ThermaProbe-9A3F2C` |
| `hostname` | `thermaprobe-<hex6>.local` | `thermaprobe-9a3f2c.local` |
| `ap_ssid` | SoftAP SSID (== probe_id) | `ThermaProbe-9A3F2C` |
| `ap_password` | `TP-<HEX8>` WPA2 key | `TP-289A3F2C` |
| `provision_secret` | Per-unit `X-Provision-Secret`, or blank if open | `s3cr-9a3f-...` |
| `fw_version` | Flashed firmware version | `2.0.0` |
| `test_wifi_ssid` | Bench Wi-Fi the unit joined in QC | `bench-2g` |
| `temperature_c` | Plausible reading observed at QC | `23.4` |
| `ingest_ok` | Bench hub ingest confirmed (`last_post_code=200`) | `yes` |
| `qc_result` | Overall gate result | `PASS` |
| `notes` | Failed-step number / rework / anything | `—` |

Example rows:

```
serial,build_date,operator,mac,probe_id,hostname,ap_ssid,ap_password,provision_secret,fw_version,test_wifi_ssid,temperature_c,ingest_ok,qc_result,notes
TP2607-001,2026-07-06,TJ,A4:CF:12:9A:3F:2C,ThermaProbe-9A3F2C,thermaprobe-9a3f2c.local,ThermaProbe-9A3F2C,TP-289A3F2C,,2.0.0,bench-2g,23.4,yes,PASS,open plug-and-play
TP2607-002,2026-07-06,TJ,A4:CF:12:7B:10:44,ThermaProbe-7B1044,thermaprobe-7b1044.local,ThermaProbe-7B1044,TP-127B1044,q7Kd-2m9,2.0.0,bench-2g,22.9,yes,PASS,locked (secret set)
```
