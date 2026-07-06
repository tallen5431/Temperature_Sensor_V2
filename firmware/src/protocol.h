// ============================================================================
// protocol.h  --  Shared ThermaProbe constants & hardware contract
// ============================================================================
// This header is the SINGLE SOURCE OF TRUTH for:
//   * firmware version + protocol version reported everywhere
//   * GPIO pin assignments for the sensor / status LED / thermocouple SPI
//   * SoftAP setup-network parameters
//   * the probe-id / hostname / SSID derivation rules
//
// IMPORTANT: The pin numbers below are referenced by docs/BOM.md and
// docs/ASSEMBLY.md.  Hardware wiring, the bill of materials and this firmware
// MUST stay in agreement -- change a pin here and the docs must change too, or
// the manufactured hardware and the flashed firmware will drift apart.
// ============================================================================
#pragma once

#include <Arduino.h>

// ---------------------------------------------------------------------------
// Versioning (matches ThermaHub CANONICAL SPEC: fw semver, proto v1)
// ---------------------------------------------------------------------------
#define THERMAPROBE_FW_VERSION "2.0.0"   // semver, advertised as TXT fw=<...>
#define THERMAPROBE_PROTO      1         // wire protocol version, TXT proto=1

// ---------------------------------------------------------------------------
// GPIO PIN MAP  (ESP32-WROOM-32E)  --  keep in sync with docs/BOM.md + ASSEMBLY
// ---------------------------------------------------------------------------
// DS18B20 (default sensor): DATA on ONE_WIRE_BUS with a 4.7k pull-up to 3V3.
#define ONE_WIRE_BUS   4     // GPIO4  -> DS18B20 DQ (needs 4.7k pull-up to 3V3)

// Status LED: on-board LED of most ESP32 dev boards is GPIO2.
#define STATUS_LED     2     // GPIO2  -> status LED (active-high)
#define STATUS_LED_ACTIVE_HIGH 1

// Optional MAX31855 K-type thermocouple (only used when -D SENSOR_MAX31855).
// Hardware SPI (VSPI) pins on the ESP32; CS is a plain GPIO.
#define MAX31855_CS    5     // GPIO5  -> MAX31855 CS
#define MAX31855_SCK   18    // GPIO18 -> MAX31855 SCK  (VSPI SCK)
#define MAX31855_MISO  19    // GPIO19 -> MAX31855 SO   (VSPI MISO)
// (MAX31855 has no MOSI; it is read-only.)

// ---------------------------------------------------------------------------
// SoftAP setup network (used when the probe has no saved Wi-Fi credentials)
// ---------------------------------------------------------------------------
// SSID is "ThermaProbe-<HEX6>" (see identity rules). The AP is WPA2-protected;
// the password is per-unit and printed on the unit label / QR (see below).
#define AP_CHANNEL          1
#define AP_MAX_CONNECTIONS  4
#define CAPTIVE_PORTAL_IP   "192.168.4.1"   // config page lives here
#define DNS_PORT            53
#define HTTP_PORT           80              // probe HTTP server + mDNS port

// ---------------------------------------------------------------------------
// Defaults for provisionable settings (overwritten by NVS / hub /provision)
// ---------------------------------------------------------------------------
#define DEFAULT_INTERVAL_MS 5000            // post cadence until hub provisions
#define MIN_INTERVAL_MS     1000
#define MAX_INTERVAL_MS     3600000UL       // 1 hour ceiling

// Plausible-reading window (mirrors the hub's -60..150 C ingest validation).
#define TEMP_MIN_C  (-60.0f)
#define TEMP_MAX_C  (150.0f)

// ---------------------------------------------------------------------------
// IDENTITY DERIVATION  (must match the hub + docs exactly)
// ---------------------------------------------------------------------------
//   HEX6      = UPPERCASE hex of the LAST 3 bytes of the ESP32 efuse (base STA)
//               MAC, i.e. mac[3]mac[4]mac[5]  -> 6 hex chars, e.g. "9A3F2C".
//   probe_id  = "ThermaProbe-" + HEX6           e.g. "ThermaProbe-9A3F2C"
//   hostname  = "thermaprobe-" + lowercase(HEX6) e.g. "thermaprobe-9a3f2c"
//               (advertised as thermaprobe-9a3f2c.local.)
//   SoftAP SSID = "ThermaProbe-" + HEX6          (same as probe_id)
//   AP password = "TP-" + UPPERCASE hex of the LAST 4 MAC bytes (8 hex chars)
//                 -> 11-char WPA2 key, e.g. "TP-289A3F2C".  factory_flash.py
//                 computes the identical string from esptool's read_mac so the
//                 printed unit label always matches what the firmware runs.
//
// The probe_id is echoed three ways that MUST all agree at runtime:
//   * mDNS TXT  id=<probe_id>
//   * HTTP header X-Probe-ID on every ingest POST
//   * JSON body field "probe_id" on every ingest POST
// main.cpp asserts/logs this invariant at boot.
// ---------------------------------------------------------------------------
#define PROBE_ID_PREFIX "ThermaProbe-"
#define HOSTNAME_PREFIX "thermaprobe-"
#define AP_PASSWORD_PREFIX "TP-"

// mDNS service advertised by the probe (hub browses for this).
//   Full type: _temps-probe._tcp.local. on TCP port 80.
// ESPmDNS wants the bare service + proto (it adds the underscores).
#define MDNS_SERVICE "temps-probe"
#define MDNS_PROTO   "tcp"
