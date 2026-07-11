// ============================================================================
// protocol.h  --  Shared TempSensor constants & hardware contract
// ============================================================================
// CANONICAL FIRMWARE: the shipping implementation is the Arduino sketch
//   esp32_temp_probe/esp32_temp_probe.ino
// -- the deep-sleep battery firmware (WiFiManager captive-portal setup +
// LittleFS offline buffer + NTP time).  That sketch is self-contained; this
// header is NOT compiled into it.  protocol.h is the human-readable CONTRACT the
// sketch follows and the SINGLE SOURCE OF TRUTH that the hardware docs
// (docs/BOM.md, docs/ASSEMBLY.md) copy their pin numbers from.
//
// If the sketch changes a pin or the identity scheme, update this header AND the
// docs together, or the manufactured hardware, the flashed firmware and the
// paper docs will drift apart.
//
// What this header pins down:
//   * firmware version + protocol version reported by the sketch
//   * GPIO pin assignments for the DS18B20 sensor + status LED
//   * SoftAP setup-network parameters (open network, per-unit SSID)
//   * the probe-id / SSID / mDNS-host derivation rules
// ============================================================================
#pragma once

#include <Arduino.h>

// ---------------------------------------------------------------------------
// Versioning (matches esp32_temp_probe.ino: FW_VERSION, protocol v1)
// ---------------------------------------------------------------------------
#define TEMPSENSOR_FW_VERSION "2.4.0"   // == FW_VERSION in the .ino
#define TEMPSENSOR_PROTO      1         // wire protocol version

// ---------------------------------------------------------------------------
// GPIO PIN MAP  (ESP32-WROOM-32E)  --  keep in sync with docs/BOM.md + ASSEMBLY
// ---------------------------------------------------------------------------
// DS18B20 is the ONLY sensor in the current firmware: DATA on ONE_WIRE_BUS with
// a 4.7k pull-up to 3V3.  (Matches `#define ONE_WIRE_BUS 5` in the .ino.)
#define ONE_WIRE_BUS   5     // GPIO5  -> DS18B20 DQ (needs 4.7k pull-up to 3V3)

// Status LED: on-board LED of most ESP32 dev boards is GPIO2 (LED_BUILTIN).
#define STATUS_LED     2     // GPIO2  -> status LED (active-high)
#define STATUS_LED_ACTIVE_HIGH 1

// ---- FUTURE / OPTIONAL sensors -- NOT in the current firmware --------------
// The shipping sketch is DS18B20-only.  Nothing below is wired, read, or
// build-selectable today; these are reserved reference pins for possible future
// variants.  Do NOT populate them on production units and do NOT treat them as
// shipping wiring.
//
// MAX31855 K-type thermocouple (hardware VSPI; read-only, no MOSI). Its old CS
// pin (GPIO5) is now the DS18B20 data pin, so a future thermocouple build must
// relocate CS to a free GPIO:
// #define MAX31855_CS  <pick a free GPIO>   // (future) MAX31855 CS
#define MAX31855_SCK   18    // (future) GPIO18 -> MAX31855 SCK  (VSPI SCK)
#define MAX31855_MISO  19    // (future) GPIO19 -> MAX31855 SO   (VSPI MISO)
// SHT4x temperature + humidity (I2C; a hub would compute VPD from temp + RH):
#define I2C_SDA        21    // (future) GPIO21 -> SHT4x SDA
#define I2C_SCL        22    // (future) GPIO22 -> SHT4x SCL

// ---------------------------------------------------------------------------
// SoftAP setup network (used when the probe has no saved Wi-Fi credentials)
// ---------------------------------------------------------------------------
// SSID == the probe id, e.g. "TempSensor-9A3F2C" (per-unit unique).  The AP is
// OPEN (no password) -- it only exists during first-time setup and is torn down
// once the probe joins the home Wi-Fi, so an open network keeps setup one-tap
// simple.  WiFiManager serves the captive setup portal at 192.168.4.1.  (A
// per-unit WPA2 key can be reintroduced for higher-security deployments.)
#define AP_CHANNEL          1
#define AP_MAX_CONNECTIONS  4
#define CAPTIVE_PORTAL_IP   "192.168.4.1"   // WiFiManager config page lives here
#define DNS_PORT            53
#define HTTP_PORT           80              // probe HTTP server + mDNS port

// ---------------------------------------------------------------------------
// Power / sleep behaviour (documents the .ino; see DEEP_SLEEP_MIN_MS there)
// ---------------------------------------------------------------------------
// The probe is a rechargeable-lithium battery device.  When the configured read
// interval is >= ~10 s the firmware deep-sleeps between readings (idle current
// <1 mA); below that it stays always-on with WiFi modem sleep and the web server
// + mDNS remain continuously reachable.  Readings taken while offline are
// buffered to LittleFS (/buf.csv) and flushed to the hub when the network
// returns.
#define DEEP_SLEEP_MIN_MS   10000UL         // interval >= this -> deep sleep

// ---------------------------------------------------------------------------
// Defaults for provisionable settings (overwritten by NVS / hub /provision)
// ---------------------------------------------------------------------------
#define DEFAULT_INTERVAL_MS 5000            // cfg_interval default in the .ino
#define MIN_INTERVAL_MS     500             // firmware clamps interval up to >= 500 ms
#define MAX_INTERVAL_MS     3600000UL       // documentation ceiling (not clamped in fw)

// Plausible-reading window (mirrors the hub's -60..150 C ingest validation; the
// hub, not the probe, enforces this).
#define TEMP_MIN_C  (-60.0f)
#define TEMP_MAX_C  (150.0f)

// ---------------------------------------------------------------------------
// IDENTITY DERIVATION  (must match the sketch + docs exactly)
// ---------------------------------------------------------------------------
//   HEX6      = 6 UPPERCASE hex chars.  Taken from the LAST 6 hex (3 bytes) of
//               the DS18B20 sensor ROM code when the 1-Wire sensor reads
//               (globally unique per Dallas part); if no sensor is present at
//               first boot it FALLS BACK to the last 6 hex of the ESP32 efuse
//               MAC (chip id).  e.g. "9A3F2C".
//   probe_id  = "TempSensor-" + HEX6            e.g. "TempSensor-9A3F2C"
//               DERIVED ONCE and PERSISTED IN NVS on first boot, then reused for
//               the life of the unit -- a later failed ROM read can no longer
//               flip the identity (see stableProbeId() in the .ino).
//   mDNS host = probe_id -> "<probe_id>.local"   e.g. "TempSensor-9A3F2C.local"
//   SoftAP SSID = probe_id                        (same string as probe_id)
//   AP password = NONE. The setup AP is OPEN -- it only exists during first-time
//                 setup and disappears once the probe joins the home Wi-Fi, so an
//                 open network keeps setup one-tap simple. (A per-unit WPA2 key
//                 can be reintroduced for higher-security deployments.)
//
// Machine-readable boot line consumed by factory_flash.py (printed every boot):
//   [label] probe_id=<id> ap_ssid=<id> ap_pass=none
//
// The probe_id is echoed three ways that MUST all agree at runtime:
//   * mDNS TXT  id=<probe_id>   (and name=<probe_id>)
//   * HTTP header X-Probe-ID on every ingest POST
//   * JSON body field "probe_id" on every ingest POST
// The sketch logs the id and the "[label]" line at boot.
// ---------------------------------------------------------------------------
#define PROBE_ID_PREFIX     "TempSensor-"
// (The setup AP is open, so there is no AP-password prefix.)

// mDNS service advertised by the probe (hub browses for this).
//   Full type: _temps-probe._tcp.local. on TCP port 80, TXT id=<probe_id>,
//   name=<probe_id>.  (No fw/proto TXT records in the current firmware.)
// ESPmDNS wants the bare service + proto (it adds the underscores).
#define MDNS_SERVICE "temps-probe"
#define MDNS_PROTO   "tcp"
