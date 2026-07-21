// ESP32 + DS18B20 + WiFiManager + mDNS + OTA + WebServer
// v2.5.0 — (a) millisecond timestamps: readings are stamped to ms precision so a
//           high-rate cadence (e.g. 0.5 s while a freezer door is open) stays
//           distinguishable instead of collapsing onto one whole-second stamp.
//           (b) disturbance burst: in deep-sleep mode a wake reading that jumps
//           more than BURST_DELTA_C from the previous one (a freezer door
//           opening, a compressor kick) makes the probe stay awake, keep Wi-Fi
//           up, sample fast and flush the offline buffer hard for a short window
//           before sleeping again — so a brief event and the connectivity window
//           it opens aren't slept through. (True wake-on-temperature would need
//           an analog sensor + comparator on a wake pin — a hardware revision.)
// v1.6.0 — stable probe identity: the probe id is derived once (DS18B20 ROM,
//           with retry, else the chip id) and persisted to NVS, so a later
//           failed sensor read can no longer flip the identity and make the hub
//           list a single probe as two devices.
// v1.5.0 — battery sleep: when the read interval is >= DEEP_SLEEP_MIN_MS
//           (default 10 s) the device enters deep sleep between readings,
//           cutting idle current from ~100 mA to <1 mA.  For shorter
//           intervals WiFi modem sleep is used instead, keeping the web
//           server fully responsive.
//
// Requires (Library Manager):
//   - WiFiManager by tzapu
//   - ArduinoJson  (v6 or v7)
//   - DallasTemperature + OneWire
//   - LittleFS (bundled with ESP32 Arduino core ≥ 2.0)
//
// Partition scheme (Arduino IDE → Tools → Partition Scheme):
//   Recommended: "No OTA (2MB APP/2MB SPIFFS)"
//   2 MB LittleFS → ~38 000 readings (~26 h at 2 s, ~65 h at 5 s).

#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiManager.h>
#include <WebServer.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <ESPmDNS.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <LittleFS.h>
#include <time.h>
#include <esp_sleep.h>

// ---------------- Pins & LED ------------------------------------------------
#define ONE_WIRE_BUS 5

// Status LED — auto-selected by build target so one firmware image fits both boards:
//   * ESP32-C3 SuperMini (the rev-1 board): onboard LED on GPIO8, wired ACTIVE-LOW
//     (drive LOW = lit). GPIO8 is also a boot strapping pin and must be HIGH at reset;
//     the SuperMini's onboard pull-up holds it high at boot, and ledInit() drives it
//     HIGH (LED off) once the app is running, so using it as the status LED is boot-safe.
//   * ESP32-WROOM-32/-32E (fallback): onboard LED on GPIO2, ACTIVE-HIGH.
#if defined(CONFIG_IDF_TARGET_ESP32C3)
  #ifndef PIN_STATUS_LED
    #define PIN_STATUS_LED 8
  #endif
  static const bool LED_ACTIVE_LOW = true;
#else
  #ifndef LED_BUILTIN
    #define LED_BUILTIN 2
  #endif
  #define PIN_STATUS_LED LED_BUILTIN
  static const bool LED_ACTIVE_LOW = false;
#endif
static const bool LED_ENABLED    = (PIN_STATUS_LED != ONE_WIRE_BUS);

inline void ledInit()  { if (LED_ENABLED) { pinMode(PIN_STATUS_LED, OUTPUT); digitalWrite(PIN_STATUS_LED, LED_ACTIVE_LOW ? HIGH : LOW); } }
inline void ledOn()    { if (LED_ENABLED) digitalWrite(PIN_STATUS_LED, LED_ACTIVE_LOW ? LOW  : HIGH); }
inline void ledOff()   { if (LED_ENABLED) digitalWrite(PIN_STATUS_LED, LED_ACTIVE_LOW ? HIGH : LOW);  }
inline void ledBlink(uint8_t n, uint16_t onMs = 60, uint16_t offMs = 120) {
  if (!LED_ENABLED) return;
  while (n--) { ledOn(); delay(onMs); ledOff(); delay(offMs); }
}

// ---------------- Identity --------------------------------------------------
static const char* SENSOR_NAME = "Setpoint";
static const char* FW_VERSION  = "2.5.0";

// The setup SoftAP is intentionally OPEN (no password): it only exists during
// first-time Wi-Fi setup and is torn down once the probe joins the home network,
// so an open AP keeps setup one-tap simple. (A per-unit WPA2 key can be
// reintroduced for higher-security deployments — see git history / SECURITY.md.)

// ---------------- Sleep configuration --------------------------------------
// Set DEEP_SLEEP_ENABLED to false to revert to always-on behaviour (the web
// server and mDNS remain continuously reachable, at the cost of higher idle
// current).
//
// DEEP_SLEEP_MIN_MS: deep sleep is only used when the configured interval is
// at or above this threshold.  Below it the WiFi-reconnect overhead (~1–3 s)
// would consume more energy than it saves, so WiFi modem sleep is used
// instead.
//
// WEBSERVER_WINDOW_MS: how long the HTTP server stays alive after each wake
// before the device goes back to sleep.  The hub's auto-provision request
// and any browser visit must arrive within this window.  Increase it if you
// need more time to reach /provision after a config change.
//
// NTP_RESYNC_INTERVAL: re-sync with NTP every N deep-sleep wakes to correct
// accumulated RTC drift.
#define DEEP_SLEEP_ENABLED true
static const uint32_t DEEP_SLEEP_MIN_MS   = 10000UL;  // 10 s
static const uint32_t WEBSERVER_WINDOW_MS =  3000UL;  //  3 s
static const uint32_t NTP_RESYNC_INTERVAL =    30UL;  // every 30 wakes

// ---------------- Disturbance burst (freezer door / rapid change) -----------
// In deep-sleep mode the probe is asleep between wakes, so a brief event (a
// freezer door opening) and the short connectivity window it opens can be slept
// through. When a wake reading differs from the previous one by more than
// BURST_DELTA_C, the probe treats it as a disturbance: it stays awake, keeps
// Wi-Fi up, samples every BURST_SAMPLE_MS and flushes the offline buffer hard
// for BURST_WINDOW_MS before returning to deep sleep — so the event and any
// backlog reach the hub while they can. This only CATCHES an event if a
// scheduled wake lands during it, so it helps most at short/moderate intervals;
// true wake-on-temperature needs an analog sensor + comparator on a wake pin
// (a hardware revision — the DS18B20 has no interrupt output). Set to false to
// disable and keep the plain fixed-interval deep-sleep behaviour.
#define BURST_ON_DISTURBANCE  true
static const float    BURST_DELTA_C   = 1.0f;     // °C change vs last wake that counts as a disturbance
static const uint32_t BURST_WINDOW_MS = 20000UL;  // stay awake/flushing this long after one
static const uint32_t BURST_SAMPLE_MS =  1000UL;  // sample cadence during the burst

// ---------------- DS18B20 ---------------------------------------------------
OneWire           oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

// 9-bit resolution → ~94 ms conversion. setWaitForConversion(false) means
// requestTemperatures() returns instantly and the loop never blocks.
static const uint8_t  DS_RESOLUTION_BITS = 9;
static const uint16_t DS_CONV_MS         = 94;

// ---------------- Config (NVS) ----------------------------------------------
Preferences prefs;   // namespace: "tscfg"
String   cfg_server_url = "";
String   cfg_token      = "";
uint32_t cfg_interval   = 5000;   // ms between readings

// ---------------- WiFiManager parameters ------------------------------------
WiFiManager wm;
WiFiManagerParameter p_server  ("server",   "Server URL",             "",     128);
WiFiManagerParameter p_token   ("token",    "Ingest token (optional)","",      64);
WiFiManagerParameter p_interval("interval", "Read interval (ms)",     "5000",  10);

// ---------------- HTTP server -----------------------------------------------
WebServer http(80);

// ---------------- Cached identity (computed once per boot) ------------------
static String g_chipId;
static String g_romHex;
static String g_probeId;
static String g_instanceName;

// ---------------- Offline buffer (LittleFS) ---------------------------------
// Each line in the buffer file: "TIMESTAMP,TEMP_C,TEMP_F,PROBE_ID\n"
// ~50 bytes/line.
static const char*    BUFFER_FILE      = "/buf.csv";
static const uint32_t BUFFER_MAX_BYTES = 1900UL * 1024UL;  // 1.9 MB cap
static const uint32_t BUFFER_MIN_FREE  =    8UL * 1024UL;  // 8 KB FS headroom
static const char*    BUF_POS_KEY = "buf_pos";

// ---------------- RTC memory (survives deep sleep) --------------------------
// These variables live in the ESP32 RTC slow-memory SRAM and retain their
// values across deep-sleep cycles.  They are reset only on a power-cycle or
// hard chip reset.
RTC_DATA_ATTR static uint32_t rtc_bootCount    = 0;    // wake counter
RTC_DATA_ATTR static bool     rtc_timeValid    = false; // true once NTP has synced
RTC_DATA_ATTR static int64_t  rtc_epochAtSleep = 0;    // unix epoch saved before sleep
RTC_DATA_ATTR static uint32_t rtc_sleepMs      = 0;    // intended sleep duration
RTC_DATA_ATTR static float    rtc_lastReadingC = -999.0f; // last temp (across sleep) for disturbance detection; -999 = unset

// ---------------- State -----------------------------------------------------
static bool          g_timeValid     = false;
static unsigned long g_lastSend      = 0;
static unsigned long g_convReqAt     = 0;
static bool          g_convPending   = false;
static float         g_lastC         = NAN;
static unsigned long g_lastAtMs      = 0;
static bool          g_wasConnected  = false;
static unsigned long g_lastFlushAt   = 0;
static unsigned long g_wakeStart     = 0;   // millis() at top of setup()
static bool          g_deepSleepMode = false;

// ============================================================================
// Time helpers
// ============================================================================

// Call once after WiFi connects.  Blocks up to 8 s waiting for SNTP.
void syncTime() {
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
  Serial.print("[NTP] Syncing...");
  struct tm ti;
  if (getLocalTime(&ti, 8000)) {
    g_timeValid = rtc_timeValid = true;
    char buf[32];
    strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &ti);
    Serial.printf(" OK (%s)\n", buf);
  } else {
    Serial.println(" FAILED — readings will not be buffered until time syncs.");
  }
}

// Returns current UTC time as an ISO 8601 string WITH milliseconds
// ("2026-07-21T00:42:04.500Z"), or "" if time is unknown. Sub-second precision
// keeps a high-rate cadence (down to the 500 ms floor) distinguishable instead
// of collapsing multiple readings onto one whole-second stamp. Seconds and
// milliseconds are taken from the same gettimeofday() call so they can't skew.
String nowIso() {
  if (!g_timeValid) return "";
  struct timeval tv;
  if (gettimeofday(&tv, nullptr) != 0 || tv.tv_sec < 1000000000L) return "";
  struct tm ti;
  gmtime_r(&tv.tv_sec, &ti);  // configTime(0,0,...) runs the clock in UTC
  char buf[32];
  size_t n = strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%S", &ti);
  snprintf(buf + n, sizeof(buf) - n, ".%03ldZ", (long)(tv.tv_usec / 1000));
  return String(buf);
}

// ============================================================================
// NVS helpers
// ============================================================================
void loadConfig() {
  if (!prefs.begin("tscfg", true)) return;
  cfg_server_url = prefs.getString("server_url", cfg_server_url);
  cfg_token      = prefs.getString("token",      cfg_token);
  cfg_interval   = prefs.getUInt  ("interval",   cfg_interval);
  prefs.end();
}

void saveConfig() {
  if (!prefs.begin("tscfg", false)) return;
  prefs.putString("server_url", cfg_server_url);
  prefs.putString("token",      cfg_token);
  prefs.putUInt  ("interval",   cfg_interval);
  prefs.end();
}

uint32_t loadBufPos() {
  if (!prefs.begin("tscfg", true)) return 0;
  uint32_t pos = prefs.getUInt(BUF_POS_KEY, 0);
  prefs.end();
  return pos;
}

void saveBufPos(uint32_t pos) {
  if (!prefs.begin("tscfg", false)) return;
  prefs.putUInt(BUF_POS_KEY, pos);
  prefs.end();
}

// ============================================================================
// Offline buffer
// ============================================================================

void bufferAppend(const String& ts, float tC, float tF) {
  if (ts.length() == 0) return;

  if (LittleFS.exists(BUFFER_FILE)) {
    File f = LittleFS.open(BUFFER_FILE, "r");
    uint32_t sz = f ? f.size() : 0;
    if (f) f.close();
    if (sz >= BUFFER_MAX_BYTES) {
      Serial.printf("[Buffer] Cap reached (%u KB) — reading dropped."
                    " Connect to hub to flush.\n", sz / 1024);
      return;
    }
  }

  uint32_t freeBytes = LittleFS.totalBytes() - LittleFS.usedBytes();
  if (freeBytes < BUFFER_MIN_FREE) {
    Serial.printf("[Buffer] Filesystem full (%u bytes free) — reading dropped."
                  " Connect to hub to flush.\n", freeBytes);
    return;
  }

  File f = LittleFS.open(BUFFER_FILE, "a");
  if (!f) { Serial.println("[Buffer] Could not open buffer file."); return; }
  f.printf("%s,%.3f,%.3f,%s\n", ts.c_str(), tC, tF, g_probeId.c_str());
  f.close();
  Serial.printf("[Buffer] Saved (ts=%s tC=%.2f)  free=%u KB\n",
                ts.c_str(), tC, freeBytes / 1024);
}

// POST a single reading with an explicit timestamp.  Returns true on HTTP 2xx.
bool postWithTimestamp(const String& ts, float tC, float tF,
                       const String& pid) {
  if (WiFi.status() != WL_CONNECTED || cfg_server_url.length() == 0)
    return false;

  StaticJsonDocument<256> doc;
  if (ts.length()) doc["timestamp"]     = ts;
  doc["temperature_c"] = tC;
  doc["temperature_f"] = tF;
  doc["probe_id"]      = pid;

  String body;
  serializeJson(doc, body);

  HTTPClient httpc;
  httpc.begin(cfg_server_url);
  httpc.setTimeout(3000);
  httpc.addHeader("Content-Type", "application/json");
  if (cfg_token.length()) httpc.addHeader("X-Token",    cfg_token);
  httpc.addHeader("X-Probe-ID", pid);

  int code = httpc.POST((uint8_t*)body.c_str(), body.length());
  httpc.end();
  return (code >= 200 && code < 300);
}

// Upload every reading stored in the buffer file, then delete it.
// Byte-offset of the next line is persisted in NVS after every successful
// POST so a mid-flush drop can resume without duplicates.
void bufferFlush() {
  if (!LittleFS.exists(BUFFER_FILE)) return;

  File f = LittleFS.open(BUFFER_FILE, "r");
  if (!f) return;

  uint32_t fileSize = f.size();
  uint32_t pos      = loadBufPos();

  if (pos >= fileSize) {
    f.close();
    LittleFS.remove(BUFFER_FILE);
    saveBufPos(0);
    return;
  }

  Serial.printf("[Buffer] Flushing from offset %u / %u bytes...\n",
                pos, fileSize);
  f.seek(pos);

  int uploaded = 0, failed = 0;

  while (f.available()) {
    http.handleClient();

    String line = f.readStringUntil('\n');
    line.trim();
    if (line.length() == 0) { pos = f.position(); continue; }

    int c1 = line.indexOf(',');
    int c2 = (c1 >= 0) ? line.indexOf(',', c1 + 1) : -1;
    int c3 = (c2 >= 0) ? line.indexOf(',', c2 + 1) : -1;
    if (c1 < 0 || c2 < 0 || c3 < 0) {
      pos = f.position();
      saveBufPos(pos);
      continue;
    }

    String ts  = line.substring(0, c1);
    float  tC  = line.substring(c1 + 1, c2).toFloat();
    float  tF  = line.substring(c2 + 1, c3).toFloat();
    String pid = line.substring(c3 + 1);

    if (postWithTimestamp(ts, tC, tF, pid)) {
      pos = f.position();
      saveBufPos(pos);
      uploaded++;
      Serial.printf("[Buffer] Uploaded %d  (ts=%s tC=%.1f)\n",
                    uploaded, ts.c_str(), tC);
    } else {
      failed++;
      Serial.printf("[Buffer] POST failed at offset %u — will retry later.\n", pos);
      break;
    }
  }

  f.close();

  if (failed == 0) {
    LittleFS.remove(BUFFER_FILE);
    saveBufPos(0);
    Serial.printf("[Buffer] Flush complete — %d readings uploaded.\n", uploaded);
  } else {
    Serial.printf("[Buffer] Partial flush: %d uploaded, stopped. "
                  "Will retry on next reconnect.\n", uploaded);
  }
}

// ============================================================================
// HTTP helpers
// ============================================================================
void addCORS() {
  http.sendHeader("Access-Control-Allow-Origin",  "*");
  http.sendHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  http.sendHeader("Access-Control-Allow-Headers", "Content-Type");
}

void sendJSON(int code, const JsonDocument& doc) {
  String out;
  serializeJson(doc, out);
  addCORS();
  http.send(code, "application/json", out);
}

void handleOptions() { addCORS(); http.send(204); }

// ============================================================================
// mDNS
// ============================================================================
void mdnsAdvertise() {
  MDNS.end();
  String host = g_instanceName;
  host.replace(".", "-");
  if (!MDNS.begin(host.c_str())) { Serial.println("[mDNS] init failed"); return; }
  MDNS.addService("_temps-probe", "_tcp", 80);
  MDNS.addServiceTxt("_temps-probe", "_tcp", "id",   g_probeId);
  MDNS.addServiceTxt("_temps-probe", "_tcp", "name", g_instanceName);
  Serial.printf("[mDNS] advertising %s as _temps-probe._tcp\n",
                g_instanceName.c_str());
}

// ============================================================================
// Web server handlers
// ============================================================================
void handleRoot() {
  String tempBlock;
  if (!isnan(g_lastC)) {
    float tF = DallasTemperature::toFahrenheit(g_lastC);
    unsigned long ageSec = (millis() - g_lastAtMs) / 1000UL;
    char ageStr[32];
    if (ageSec < 60)
      snprintf(ageStr, sizeof(ageStr), "%lus ago", ageSec);
    else
      snprintf(ageStr, sizeof(ageStr), "%lum %lus ago", ageSec / 60, ageSec % 60);

    char tBuf[64];
    snprintf(tBuf, sizeof(tBuf), "%.2f &deg;C &nbsp;/&nbsp; %.2f &deg;F", g_lastC, tF);

    tempBlock = String("<div style='margin:16px 0;padding:14px 20px;"
                       "background:#f0f4ff;border-left:4px solid #3a7bd5;"
                       "border-radius:4px;font-family:monospace'>")
      + "<span style='font-size:2rem;font-weight:bold'>" + tBuf + "</span><br>"
      + "<small style='color:#555'>Last reading: " + String(nowIso()) + "  (" + ageStr + ")</small>"
      + "</div>";
  } else {
    tempBlock = "<p style='color:#c00'><b>&#9888; No temperature reading yet.</b> "
                "Check DS18B20 wiring on GPIO " + String(ONE_WIRE_BUS) + ".</p>";
  }

  String sleepRow;
  if (g_deepSleepMode) {
    sleepRow = "<tr><td>Sleep mode</td><td>Deep sleep ("
               + String(WEBSERVER_WINDOW_MS / 1000) + " s window)</td></tr>";
  } else {
    sleepRow = "<tr><td>Sleep mode</td><td>WiFi modem sleep</td></tr>";
  }

  String html = String("<!doctype html><meta charset='utf-8'>"
                        "<meta http-equiv='refresh' content='5'>")
    + "<style>body{font-family:sans-serif;max-width:520px;margin:32px auto;padding:0 16px}"
      "table{border-collapse:collapse;width:100%}td{padding:5px 8px}"
      "tr:nth-child(even){background:#f7f7f7}</style>"
    + "<h3>" + SENSOR_NAME + " " + FW_VERSION + "</h3>"
    + tempBlock
    + "<table>"
    + "<tr><td>ID</td><td><b>"       + g_probeId                          + "</b></td></tr>"
    + "<tr><td>Server</td><td>"      + cfg_server_url                     + "</td></tr>"
    + "<tr><td>Interval</td><td>"    + String(cfg_interval)               + " ms</td></tr>"
    + "<tr><td>Time valid</td><td>"  + (g_timeValid ? "yes" : "no")       + "</td></tr>"
    + "<tr><td>WiFi RSSI</td><td>"   + String(WiFi.RSSI())                + " dBm</td></tr>"
    + "<tr><td>Uptime</td><td>"      + String(millis() / 1000UL)          + " s</td></tr>"
    + sleepRow
    + "<tr><td>Wake #</td><td>"      + String(rtc_bootCount)              + "</td></tr>"
    + "</table>";

  if (LittleFS.exists(BUFFER_FILE)) {
    File f = LittleFS.open(BUFFER_FILE, "r");
    uint32_t sz = f ? f.size() : 0;
    if (f) f.close();
    uint32_t pos = loadBufPos();
    html += "<p><b>Buffered: " + String((sz - pos) / 50) +
            " est. readings (" + String((sz - pos) / 1024) + " KB pending)</b></p>";
  }

  html += "<p style='color:#aaa;font-size:0.8rem'>Page auto-refreshes every 5 s</p>";
  http.send(200, "text/html", html);
}

void handleWhoAmI() {
  StaticJsonDocument<320> doc;
  doc["id"]          = g_probeId;
  doc["name"]        = g_instanceName;
  doc["mac"]         = g_chipId;
  doc["ds18b20_rom"] = g_romHex;
  doc["fw_version"]  = FW_VERSION;
  doc["interval_ms"] = cfg_interval;
  doc["server_url"]  = cfg_server_url;
  doc["time_valid"]  = g_timeValid;
  sendJSON(200, doc);
}

void handleStatus() {
  StaticJsonDocument<384> doc;
  doc["id"]          = g_probeId;
  doc["interval_ms"] = cfg_interval;
  doc["server_url"]  = cfg_server_url;
  doc["time_valid"]  = g_timeValid;
  if (!isnan(g_lastC)) {
    doc["last_c"]  = g_lastC;
    doc["last_ms"] = g_lastAtMs;
    doc["last_ts"] = nowIso();
  }
  if (LittleFS.exists(BUFFER_FILE)) {
    File f = LittleFS.open(BUFFER_FILE, "r");
    uint32_t sz = f ? f.size() : 0;
    if (f) f.close();
    uint32_t pos = loadBufPos();
    doc["buffered_bytes"]    = sz - pos;
    doc["buffered_est_rows"] = (sz - pos) / 50;
  } else {
    doc["buffered_bytes"]    = 0;
    doc["buffered_est_rows"] = 0;
  }
  doc["fs_total_kb"] = LittleFS.totalBytes() / 1024;
  doc["fs_free_kb"]  = (LittleFS.totalBytes() - LittleFS.usedBytes()) / 1024;
  doc["sleep_mode"]  = g_deepSleepMode ? "deep" : "modem";
  doc["wake_count"]  = rtc_bootCount;
  sendJSON(200, doc);
}

void handleProvision() {
  if (http.method() == HTTP_OPTIONS) return handleOptions();
  if (http.method() != HTTP_POST) {
    StaticJsonDocument<64> e; e["ok"] = false; e["error"] = "POST required";
    return sendJSON(405, e);
  }

  StaticJsonDocument<256> doc;
  DeserializationError err = deserializeJson(doc, http.arg("plain"));
  if (err) {
    StaticJsonDocument<64> e; e["ok"] = false; e["error"] = "bad json";
    return sendJSON(400, e);
  }

  String   url      = doc["server_url"] | "";
  String   tok      = doc["token"]      | "";
  uint32_t interval = (uint32_t)(doc["interval_ms"] | cfg_interval);

  if (url.length() == 0) {
    StaticJsonDocument<64> e; e["ok"] = false; e["error"] = "server_url required";
    return sendJSON(400, e);
  }

  cfg_server_url = url;
  cfg_token      = tok;
  cfg_interval   = interval < 500 ? 500 : interval;
  saveConfig();

  StaticJsonDocument<128> out;
  out["ok"]          = true;
  out["server_url"]  = cfg_server_url;
  out["interval_ms"] = cfg_interval;
  sendJSON(200, out);
}

// ============================================================================
// WiFi portal
// ============================================================================
void startConfigPortal() {
  // The setup AP is the per-unit probe id (unique SSID) and is OPEN (no password).
  String apName = g_probeId;

  wm.setClass("invert");
  wm.setTitle(String(SENSOR_NAME) + " (" + FW_VERSION + ")");
  wm.setConfigPortalBlocking(true);
  wm.setParamsPage(true);

  p_server.setValue(cfg_server_url.c_str(), cfg_server_url.length());
  p_token.setValue (cfg_token.c_str(),      cfg_token.length());
  char ibuf[12];
  snprintf(ibuf, sizeof(ibuf), "%lu", (unsigned long)cfg_interval);
  p_interval.setValue(ibuf, strlen(ibuf));

  // Parameters were registered once in setup() — do NOT re-add here.

  Serial.println("[WiFi] Starting config portal...");
  ledBlink(2, 50, 100);

  if (wm.startConfigPortal(apName.c_str())) {   // open AP (no password)
    cfg_server_url = String(p_server.getValue());
    cfg_token      = String(p_token.getValue());
    cfg_interval   = strtoul(p_interval.getValue(), nullptr, 10);
    if (cfg_interval < 500) cfg_interval = 500;
    saveConfig();
    Serial.println("[WiFi] Portal saved & connected.");
    Serial.print("[WiFi] IP: "); Serial.println(WiFi.localIP());
    ledBlink(3, 120, 120);
  } else {
    Serial.println("[WiFi] Portal closed without connection.");
  }
}

// ============================================================================
// Identity helpers
// ============================================================================
String chipIdHex() {
  uint32_t lo = (uint32_t)(ESP.getEfuseMac() & 0xFFFFFFFFULL);
  char buf[9]; snprintf(buf, sizeof(buf), "%08X", lo);
  return String(buf);
}

String ds18b20RomHex() {
  DeviceAddress addr;
  if (!sensors.getAddress(addr, 0)) return "";
  char buf[17];
  for (int i = 0; i < 8; i++) sprintf(buf + i * 2, "%02X", addr[i]);
  buf[16] = '\0';
  return String(buf);
}

String buildProbeId(const String& rom, const String& chip) {
  // "Setpoint-<HEX6>": 6 uppercase hex, wide enough that a manufacturing
  // batch won't collide. Derived from the DS18B20 ROM (globally unique) when the
  // sensor reads, else from the chip's efuse MAC. Persisted by stableProbeId().
  String hex;
  if (rom.length() >= 6)  hex = rom.substring(rom.length() - 6);
  else if (chip.length() >= 6) hex = chip.substring(chip.length() - 6);
  else hex = (rom.length() ? rom : chip);
  hex.toUpperCase();
  return "Setpoint-" + hex;
}

// Read the DS18B20 ROM with a few retries.  On a cold boot the 1-Wire bus can
// need a moment to settle; without this the first read sometimes fails and the
// probe id would fall back to the (different) chip-based name.
String ds18b20RomHexRetry() {
  for (uint8_t i = 0; i < 5; i++) {
    String rom = ds18b20RomHex();
    if (rom.length()) return rom;
    sensors.begin();          // re-enumerate the bus, then retry
    delay(50);
  }
  return "";
}

// Return a STABLE probe id that never changes for the life of the device.
// The first id we ever derive (ROM-based when the sensor reads, else chip-based)
// is persisted to NVS and reused on every subsequent boot, so a later failed
// ROM read cannot flip the identity and make the hub show one probe as two.
String stableProbeId(const String& rom, const String& chip) {
  String saved;
  if (prefs.begin("tscfg", true)) {
    saved = prefs.getString("probe_id", "");
    prefs.end();
  }
  if (saved.length()) return saved;          // identity already established

  String id = buildProbeId(rom, chip);
  if (prefs.begin("tscfg", false)) {
    prefs.putString("probe_id", id);
    prefs.end();
  }
  return id;
}

// ============================================================================
// Deep sleep
// ============================================================================

// Stay awake, keep Wi-Fi up, sample fast and flush the offline buffer for
// BURST_WINDOW_MS, then return so the caller can deep-sleep. Called from the
// deep-sleep path when a wake reading shows a rapid change (e.g. a freezer door
// opened) so the event AND any buffered backlog reach the hub during the
// connectivity window the disturbance opened. A closed freezer is an RF box, so
// this also retries the Wi-Fi association: the door opening may be the first
// real chance to connect.
void runDisturbanceBurst() {
  Serial.printf("[Burst] Disturbance detected — staying awake %lus to flush.\n",
                (unsigned long)(BURST_WINDOW_MS / 1000UL));
  ledBlink(1, 40, 0);
  unsigned long burstEnd   = millis() + BURST_WINDOW_MS;
  unsigned long lastSample = 0;

  while (millis() < burstEnd) {
    http.handleClient();

    if (WiFi.status() != WL_CONNECTED) {
      WiFi.begin();
      unsigned long t0 = millis();
      while (WiFi.status() != WL_CONNECTED && millis() - t0 < 4000UL) {
        http.handleClient();
        delay(50);
      }
      if (WiFi.status() == WL_CONNECTED) mdnsAdvertise();
    }
    if (WiFi.status() == WL_CONNECTED) bufferFlush();

    if (millis() - lastSample >= BURST_SAMPLE_MS) {
      lastSample = millis();
      sensors.requestTemperatures();
      delay(DS_CONV_MS + 5);
      float tC = sensors.getTempCByIndex(0);
      if (tC != DEVICE_DISCONNECTED_C) {
        float  tF = DallasTemperature::toFahrenheit(tC);
        String ts = nowIso();
        g_lastC          = tC;
        g_lastAtMs       = millis();
        rtc_lastReadingC = tC;   // keep the across-sleep baseline current
        if (WiFi.status() == WL_CONNECTED) {
          if (!postWithTimestamp(ts, tC, tF, g_probeId)) bufferAppend(ts, tC, tF);
        } else {
          bufferAppend(ts, tC, tF);
        }
      }
    }
    delay(10);
  }
  Serial.println("[Burst] Window elapsed — returning to deep sleep.");
}

// Persist time, power down WiFi and mDNS, then deep-sleep for durationMs ms.
// On wakeup the ESP32 runs setup() again from the top; the wakeup cause will
// be ESP_SLEEP_WAKEUP_TIMER so setup() takes the fast-reconnect path.
void enterDeepSleep(uint32_t durationMs) {
  // Save the current epoch so setup() can restore system time on wake without
  // an NTP round-trip.  The ESP32 RTC timer tracks elapsed time during sleep.
  rtc_epochAtSleep = (int64_t)time(nullptr);
  rtc_sleepMs      = durationMs;

  Serial.printf("[Sleep] Deep sleep %.1f s  (next wake #%u)\n",
                durationMs / 1000.0f, rtc_bootCount + 1);
  Serial.flush();

  http.stop();
  MDNS.end();
  WiFi.disconnect(true);
  delay(20);

  esp_sleep_enable_timer_wakeup((uint64_t)durationMs * 1000ULL);
  esp_deep_sleep_start();
  // never reached
}

// ============================================================================
void setup() {
  g_wakeStart = millis();
  ledInit();
  Serial.begin(115200);
  delay(150);

  // ── Detect wakeup source ──────────────────────────────────────────────────
  esp_sleep_wakeup_cause_t wakeupCause = esp_sleep_get_wakeup_cause();
  bool fromDeepSleep = (wakeupCause == ESP_SLEEP_WAKEUP_TIMER);
  rtc_bootCount++;

  Serial.printf("\n%s FW %s  wake #%u (%s)\n",
                SENSOR_NAME, FW_VERSION, rtc_bootCount,
                fromDeepSleep ? "deep-sleep timer" : "cold boot / reset");

  loadConfig();

  // DS18B20: 9-bit, non-blocking
  sensors.begin();
  sensors.setResolution(DS_RESOLUTION_BITS);
  sensors.setWaitForConversion(false);
  Serial.printf("DS18B20 sensors found: %d\n", sensors.getDeviceCount());

  // Cache identity strings.  The probe id is derived once and persisted, so it
  // stays stable across reboots even if a later DS18B20 ROM read fails.
  g_chipId       = chipIdHex();
  g_romHex       = ds18b20RomHexRetry();
  g_probeId      = stableProbeId(g_romHex, g_chipId);
  g_instanceName = g_probeId;                 // mDNS / setup-AP SSID == probe id
  Serial.printf("Probe ID:  %s\n", g_probeId.c_str());
  // Machine-readable line for factory_flash.py: id + setup-AP SSID (== id). The
  // setup AP is open (no password), so there is no key to record.
  Serial.printf("[label] probe_id=%s ap_ssid=%s ap_pass=none\n",
                g_probeId.c_str(), g_probeId.c_str());

  // Mount LittleFS — format on first use (takes ~2 s, one-time only)
  if (!LittleFS.begin(true)) {
    Serial.println("[LittleFS] Mount failed — offline buffer disabled.");
  } else {
    Serial.printf("[LittleFS] Mounted. Total: %u KB  Used: %u KB\n",
                  LittleFS.totalBytes() / 1024, LittleFS.usedBytes() / 1024);
    if (LittleFS.exists(BUFFER_FILE)) {
      File f = LittleFS.open(BUFFER_FILE, "r");
      uint32_t sz = f ? f.size() : 0;
      if (f) f.close();
      uint32_t pos = loadBufPos();
      Serial.printf("[Buffer] Pending: ~%u readings (%u KB)\n",
                    (sz - pos) / 50, (sz - pos) / 1024);
    }
  }

  // ── WiFi ──────────────────────────────────────────────────────────────────
  if (fromDeepSleep) {
    // Fast reconnect path: skip the WiFiManager portal.  WiFiManager saves
    // credentials into the ESP32 WiFi NVS so WiFi.begin() (no args) reconnects
    // to the same network as before.
    WiFi.mode(WIFI_STA);
    WiFi.begin();
    Serial.print("[WiFi] Reconnecting (deep-sleep wake)...");
    uint32_t t0 = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - t0 < 15000UL) {
      delay(100);
    }
    if (WiFi.status() == WL_CONNECTED) {
      Serial.printf(" OK (%lu ms)  IP: %s\n",
                    millis() - t0, WiFi.localIP().toString().c_str());
      g_wasConnected = true;
    } else {
      Serial.println(" FAILED — reading will be buffered.");
    }
  } else {
    // Cold boot: full WiFiManager flow (opens portal if no saved network)
    WiFi.mode(WIFI_STA);
    wm.setConnectTimeout(20);
    wm.setConfigPortalTimeout(0);
    wm.setHostname(SENSOR_NAME);

    // Register parameters exactly once
    wm.addParameter(&p_server);
    wm.addParameter(&p_token);
    wm.addParameter(&p_interval);

    // Per-unit unique, OPEN setup AP (SSID == the probe id, e.g. Setpoint-9A3F2C).
    // No password: the AP only exists during first-time setup and disappears once
    // the probe joins the home Wi-Fi, so an open network keeps setup one-tap simple.
    if (!wm.autoConnect(g_probeId.c_str())) {
      Serial.println("[WiFi] No known network; opening portal.");
      p_server.setValue(cfg_server_url.c_str(), cfg_server_url.length());
      p_token.setValue (cfg_token.c_str(),      cfg_token.length());
      char ibuf[12];
      snprintf(ibuf, sizeof(ibuf), "%lu", (unsigned long)cfg_interval);
      p_interval.setValue(ibuf, strlen(ibuf));
      startConfigPortal();
    }

    if (WiFi.status() == WL_CONNECTED) {
      Serial.print("[WiFi] Connected. IP: ");
      Serial.println(WiFi.localIP());
      g_wasConnected = true;
    }
  }

  // ── Decide sleep mode for this cycle ──────────────────────────────────────
  g_deepSleepMode = DEEP_SLEEP_ENABLED && (cfg_interval >= DEEP_SLEEP_MIN_MS);

  // In always-on (non-deep-sleep) mode enable WiFi modem sleep so the radio
  // powers down between DTIM beacons, saving ~100–150 mA during idle without
  // affecting HTTP responsiveness.
  if (!g_deepSleepMode) {
    WiFi.setSleep(true);
  }

  // ── NTP / time ────────────────────────────────────────────────────────────
  // Restore the clock from the RTC FIRST, independent of Wi-Fi. The ESP32 RTC
  // timer keeps running through deep sleep, so a probe that wakes during a
  // Wi-Fi / router outage still gets a valid timestamp — and can therefore
  // BUFFER its readings to LittleFS instead of dropping them for want of a
  // clock (bufferAppend() early-returns on an empty timestamp).
  if (fromDeepSleep && rtc_timeValid && rtc_epochAtSleep > 0) {
    time_t approxNow = (time_t)(rtc_epochAtSleep + (int64_t)(rtc_sleepMs / 1000));
    struct timeval tv = { .tv_sec = approxNow, .tv_usec = 0 };
    settimeofday(&tv, nullptr);
    g_timeValid = true;
    Serial.printf("[Time] Restored from RTC: %s\n", nowIso().c_str());
  }

  if (WiFi.status() == WL_CONNECTED) {
    // Online housekeeping: get or refresh NTP time, advertise, flush the buffer.
    if (!g_timeValid) {
      // Cold boot / never-synced — must contact NTP for an initial clock.
      syncTime();
    } else if (rtc_bootCount % NTP_RESYNC_INTERVAL == 0) {
      // Clock came from the RTC; resync periodically to correct accumulated drift.
      Serial.println("[NTP] Scheduled resync...");
      syncTime();
    }
    ledBlink(3, 120, 120);
    mdnsAdvertise();
    bufferFlush();
  }

  http.on("/",          HTTP_GET,     handleRoot);
  http.on("/whoami",    HTTP_GET,     handleWhoAmI);
  http.on("/status",    HTTP_GET,     handleStatus);
  http.on("/provision", HTTP_POST,    handleProvision);
  http.on("/provision", HTTP_OPTIONS, handleOptions);
  // NOTE: this must stay AFTER the WiFiManager config portal (autoConnect/
  // startConfigPortal above). During setup WiFiManager owns port 80 (its captive
  // portal) and port 53 (the DNS redirector that makes phones auto-pop the setup
  // page). Starting our own server here before the portal closes would clash on
  // port 80 and break the captive-portal auto-redirect.
  http.begin();

  // In deep-sleep mode take the reading on the very first loop() iteration.
  // Standard unsigned-arithmetic trick: (millis() - g_lastSend) will equal
  // cfg_interval on the first call even if millis() < cfg_interval.
  if (g_deepSleepMode) {
    g_lastSend = millis() - cfg_interval;
  }

  Serial.printf("[Setup] Ready. Mode: %s  Interval: %u ms\n",
                g_deepSleepMode ? "deep-sleep" : "always-on", cfg_interval);
}

// ============================================================================
void loop() {
  http.handleClient();

  unsigned long now       = millis();
  bool          connected = (WiFi.status() == WL_CONNECTED);

  // ── WiFi watchdog & buffer retry (always-on mode only) ───────────────────
  // In deep-sleep mode we reconnect fresh in setup() every cycle, so these
  // continuous watchdog tasks are not needed.
  if (!g_deepSleepMode) {
    if (!connected) {
      if (g_wasConnected) {
        Serial.println("[WiFi] Connection lost — readings will be buffered.");
        g_wasConnected = false;
      }
      static unsigned long lastReconnAt = 0;
      if (now - lastReconnAt >= 5000) {
        Serial.println("[WiFi] Attempting reconnect...");
        WiFi.reconnect();
        lastReconnAt = now;
      }
      // Fall through — still take readings and buffer them while offline
    }

    if (connected && !g_wasConnected) {
      Serial.print("[WiFi] Reconnected. IP: ");
      Serial.println(WiFi.localIP());
      g_wasConnected = true;
      if (!g_timeValid) syncTime();
      mdnsAdvertise();
      g_lastFlushAt = now;
      bufferFlush();
    }

    // Periodic NTP retry
    if (connected && !g_timeValid) {
      static unsigned long lastNtpRetry = 0;
      if (now - lastNtpRetry >= 60000UL) {
        lastNtpRetry = now;
        Serial.println("[NTP] Retrying time sync...");
        syncTime();
      }
    }

    // Periodic buffer retry (stops on first failed POST, retries here every 30 s)
    if (connected && LittleFS.exists(BUFFER_FILE) &&
        (now - g_lastFlushAt >= 30000UL)) {
      g_lastFlushAt = now;
      bufferFlush();
    }
  }

  // ── Phase 1: kick off a non-blocking DS18B20 conversion ───────────────────
  if (!g_convPending && (now - g_lastSend >= cfg_interval)) {
    sensors.requestTemperatures();
    g_convReqAt   = now;
    g_convPending = true;
    g_lastSend    = now;
  }

  // ── Phase 2: read result once the conversion window has elapsed ───────────
  if (g_convPending && (now - g_convReqAt >= DS_CONV_MS)) {
    g_convPending = false;
    float tC = sensors.getTempCByIndex(0);

    if (tC == DEVICE_DISCONNECTED_C) {
      Serial.println("[Temp] Sensor disconnected — reinitialising bus...");
      sensors.begin();
      sensors.setResolution(DS_RESOLUTION_BITS);
      sensors.setWaitForConversion(false);
      ledBlink(2, 60, 160);

      if (g_deepSleepMode) {
        // Sleep even on error; the sensor will be retried on next wake
        unsigned long elapsed = millis() - g_wakeStart;
        uint32_t sleepMs = cfg_interval > elapsed
                           ? (uint32_t)(cfg_interval - elapsed) : 1000UL;
        enterDeepSleep(sleepMs);
      }
      return;
    }

    float  tF = DallasTemperature::toFahrenheit(tC);
    String ts = nowIso();
    g_lastC    = tC;
    g_lastAtMs = now;

    // Disturbance detection for the deep-sleep burst: compare this reading to the
    // previous one carried across sleep in RTC memory. An abrupt change in either
    // direction (freezer door open = rise, compressor kick = fall) counts.
    bool disturbance = BURST_ON_DISTURBANCE && rtc_lastReadingC > -900.0f
                       && fabsf(tC - rtc_lastReadingC) >= BURST_DELTA_C;
    rtc_lastReadingC = tC;

    if (connected) {
      if (postWithTimestamp(ts, tC, tF, g_probeId)) {
        ledOn(); delay(20); ledOff();
      } else {
        // POST failed (hub unreachable?) — fall through to buffer
        Serial.println("[POST] Failed — buffering reading.");
        bufferAppend(ts, tC, tF);
        ledBlink(2, 80, 120);
      }
    } else {
      // Offline: store to flash
      bufferAppend(ts, tC, tF);
      ledBlink(2, 80, 120);
    }

    // ── Deep sleep ────────────────────────────────────────────────────────
    if (g_deepSleepMode) {
      // A disturbance (e.g. the freezer door just opened) means an event worth
      // capturing AND a likely connectivity window — stay awake to flush it all
      // before sleeping. Otherwise keep the HTTP server live for the usual short
      // WEBSERVER_WINDOW_MS so the hub's auto-provision (and any browser) can
      // reach us. Both are skipped when Wi-Fi is down and it's not a disturbance
      // (the server is unreachable and there's no event to chase).
      if (disturbance) {
        runDisturbanceBurst();
      } else if (connected) {
        unsigned long windowEnd = millis() + WEBSERVER_WINDOW_MS;
        while (millis() < windowEnd) {
          http.handleClient();
          delay(5);
        }
      }

      // Sleep for the remainder of the interval.
      // Unsigned arithmetic: if elapsed > cfg_interval we sleep 100 ms minimum
      // to avoid a tight reboot loop.
      unsigned long elapsed = millis() - g_wakeStart;
      uint32_t sleepMs = cfg_interval > (uint32_t)elapsed
                         ? (uint32_t)(cfg_interval - elapsed) : 100UL;
      enterDeepSleep(sleepMs);
      // never reached
    }
  }
}
