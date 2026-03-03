// ESP32 + DS18B20 + WiFiManager + mDNS + OTA + WebServer
// v1.4.0 — offline buffer: readings are stored in LittleFS flash while
//           WiFi is unavailable and uploaded (with original timestamps)
//           when the connection is restored.
//
// Requires (Library Manager):
//   - WiFiManager by tzapu
//   - ArduinoJson  (v6 or v7)
//   - DallasTemperature + OneWire
//   - ArduinoOTA, LittleFS (bundled with ESP32 Arduino core ≥ 2.0)
//
// Partition scheme (Arduino IDE → Tools → Partition Scheme):
//   Recommended: "Default 4MB with spiffs (1.2MB APP/1.5MB SPIFFS)"
//   OTA support + 1.5 MB LittleFS → ~28 000 readings (~38 h at 5 s).

#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiManager.h>
#include <WebServer.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <ESPmDNS.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <ArduinoOTA.h>
#include <LittleFS.h>
#include <time.h>

// ---------------- Pins & LED ------------------------------------------------
#define ONE_WIRE_BUS 5
#ifndef LED_BUILTIN
  #define LED_BUILTIN 2
#endif
#define PIN_STATUS_LED LED_BUILTIN
static const bool LED_ACTIVE_LOW = false;
static const bool LED_ENABLED    = (PIN_STATUS_LED != ONE_WIRE_BUS);

inline void ledInit()  { if (LED_ENABLED) { pinMode(PIN_STATUS_LED, OUTPUT); digitalWrite(PIN_STATUS_LED, LED_ACTIVE_LOW ? HIGH : LOW); } }
inline void ledOn()    { if (LED_ENABLED) digitalWrite(PIN_STATUS_LED, LED_ACTIVE_LOW ? LOW  : HIGH); }
inline void ledOff()   { if (LED_ENABLED) digitalWrite(PIN_STATUS_LED, LED_ACTIVE_LOW ? HIGH : LOW);  }
inline void ledBlink(uint8_t n, uint16_t onMs = 60, uint16_t offMs = 120) {
  if (!LED_ENABLED) return;
  while (n--) { ledOn(); delay(onMs); ledOff(); delay(offMs); }
}

// ---------------- Identity --------------------------------------------------
static const char* SENSOR_NAME = "TempSensor";
static const char* FW_VERSION  = "1.4.0";

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

// ---------------- Cached identity (computed once in setup) ------------------
static String g_chipId;
static String g_romHex;
static String g_probeId;
static String g_instanceName;

// ---------------- Offline buffer (LittleFS) ---------------------------------
// Each line in the buffer file: "TIMESTAMP,TEMP_C,TEMP_F,PROBE_ID\n"
// ~50 bytes/line.
//
// BUFFER_MAX_BYTES caps the buffer file size.  Set below the recommended
// "Default 4MB with spiffs" LittleFS partition (1.5 MB) to leave headroom
// for LittleFS metadata (superblocks, commit journal) and any other files.
//
// BUFFER_MIN_FREE is an additional guard: if the filesystem free space drops
// below this threshold the append is refused regardless of the file-size cap,
// protecting the FS from corruption if other files happen to be present.
static const char*    BUFFER_FILE      = "/buf.csv";
static const uint32_t BUFFER_MAX_BYTES = 1400UL * 1024UL;  // 1.4 MB cap (fits 1.5 MB partition)
static const uint32_t BUFFER_MIN_FREE  =    8UL * 1024UL;  // keep 8 KB free for FS metadata

// NVS key that tracks how many bytes have already been successfully uploaded
// from the current buffer file.  Survives reboots mid-flush so we never
// re-upload the same reading twice.
static const char*    BUF_POS_KEY = "buf_pos";

// ---------------- State -----------------------------------------------------
static bool          g_timeValid    = false;   // true once NTP has synced
static unsigned long g_lastSend     = 0;
static unsigned long g_convReqAt    = 0;
static bool          g_convPending  = false;
static float         g_lastC        = NAN;
static unsigned long g_lastAtMs     = 0;
static bool          g_wasConnected = false;

// ============================================================================
// Time helpers
// ============================================================================

// Call once after WiFi connects.  Blocks up to 8 s waiting for SNTP.
void syncTime() {
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
  Serial.print("[NTP] Syncing...");
  struct tm ti;
  if (getLocalTime(&ti, 8000)) {
    g_timeValid = true;
    char buf[32];
    strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &ti);
    Serial.printf(" OK (%s)\n", buf);
  } else {
    Serial.println(" FAILED — readings will not be buffered until time syncs.");
  }
}

// Returns current UTC time as ISO 8601 string, or "" if time is unknown.
// The ESP32 RTC maintains time through WiFi disconnections once synced.
String nowIso() {
  if (!g_timeValid) return "";
  struct tm ti;
  if (!getLocalTime(&ti, 0)) return "";
  char buf[25];
  strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &ti);
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

// Append one reading to the local flash buffer.
// Only called when we have a valid timestamp; readings without a known time
// are discarded rather than stored with a wrong/missing timestamp.
void bufferAppend(const String& ts, float tC, float tF) {
  if (ts.length() == 0) return;   // no valid time — skip

  // Guard 1: buffer file size cap (prevents exceeding target storage budget)
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

  // Guard 2: filesystem free-space floor (protects FS metadata even if
  // another file has consumed space, and catches partitions smaller than
  // BUFFER_MAX_BYTES such as the 190 KB "Minimal SPIFFS" scheme)
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

// POST a single reading with an explicit timestamp.
// Returns true on HTTP 2xx.
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
//
// Resilience: the byte offset of the next line to upload is persisted in NVS
// after every successful POST.  If the connection drops mid-flush, the next
// call picks up exactly where it left off — no duplicates, no data loss.
//
// Responsiveness: http.handleClient() and ArduinoOTA.handle() are called
// inside the loop so the web server stays responsive during a long flush.
void bufferFlush() {
  if (!LittleFS.exists(BUFFER_FILE)) return;

  File f = LittleFS.open(BUFFER_FILE, "r");
  if (!f) return;

  uint32_t fileSize = f.size();
  uint32_t pos      = loadBufPos();

  if (pos >= fileSize) {
    // Nothing left to upload — clean up
    f.close();
    LittleFS.remove(BUFFER_FILE);
    saveBufPos(0);
    return;
  }

  Serial.printf("[Buffer] Flushing from offset %u / %u bytes...\n",
                pos, fileSize);
  f.seek(pos);

  int uploaded = 0;
  int failed   = 0;

  while (f.available()) {
    http.handleClient();
    ArduinoOTA.handle();

    String line = f.readStringUntil('\n');
    line.trim();
    if (line.length() == 0) { pos = f.position(); continue; }

    // Parse:  TIMESTAMP , TEMP_C , TEMP_F , PROBE_ID
    // (probe_id may itself contain commas — take everything after the 3rd)
    int c1 = line.indexOf(',');
    int c2 = (c1 >= 0) ? line.indexOf(',', c1 + 1) : -1;
    int c3 = (c2 >= 0) ? line.indexOf(',', c2 + 1) : -1;
    if (c1 < 0 || c2 < 0 || c3 < 0) {
      // Malformed line — skip it
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
      saveBufPos(pos);   // persist progress so a mid-flush drop can resume here
      uploaded++;
      Serial.printf("[Buffer] Uploaded %d  (ts=%s tC=%.1f)\n",
                    uploaded, ts.c_str(), tC);
    } else {
      failed++;
      Serial.printf("[Buffer] POST failed at offset %u — will retry later.\n", pos);
      break;  // stop; resume from same pos on next reconnect
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
  String html = String("<!doctype html><meta charset='utf-8'>")
    + "<h3>" + SENSOR_NAME + " " + FW_VERSION + "</h3>"
    + "<p>ID: "       + g_probeId          + "</p>"
    + "<p>Server: "   + cfg_server_url     + "</p>"
    + "<p>Interval: " + String(cfg_interval) + " ms</p>"
    + "<p>Time valid: " + (g_timeValid ? "yes" : "no") + "</p>";

  // Buffer info
  if (LittleFS.exists(BUFFER_FILE)) {
    File f = LittleFS.open(BUFFER_FILE, "r");
    uint32_t sz = f ? f.size() : 0;
    if (f) f.close();
    uint32_t pos = loadBufPos();
    html += "<p><b>Buffered: " + String((sz - pos) / 50) +
            " est. readings (" + String((sz - pos) / 1024) + " KB pending)</b></p>";
  }
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
  StaticJsonDocument<320> doc;
  doc["id"]          = g_probeId;
  doc["interval_ms"] = cfg_interval;
  doc["server_url"]  = cfg_server_url;
  doc["time_valid"]  = g_timeValid;
  if (!isnan(g_lastC)) {
    doc["last_c"]  = g_lastC;
    doc["last_ms"] = g_lastAtMs;
    doc["last_ts"] = nowIso();
  }
  // Buffer info
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
  uint32_t chip = (uint32_t)ESP.getEfuseMac();
  char apName[32];
  snprintf(apName, sizeof(apName), "%s-%04X", SENSOR_NAME, (uint16_t)(chip & 0xFFFF));

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

  if (wm.startConfigPortal(apName)) {
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
// OTA
// ============================================================================
void setupOTA() {
  ArduinoOTA.setHostname(g_instanceName.c_str());
  ArduinoOTA.onStart([]() { Serial.println("[OTA] Starting..."); ledBlink(3, 50, 50); });
  ArduinoOTA.onEnd  ([]()              { Serial.println("[OTA] Done."); });
  ArduinoOTA.onError([](ota_error_t e) { Serial.printf("[OTA] Error[%u]\n", e); });
  ArduinoOTA.begin();
  Serial.println("[OTA] Ready");
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
  if (rom.length() >= 4) return "TempProbe-"  + rom.substring(rom.length() - 4);
  return                        "TempSensor-" + chip.substring(4);
}

// ============================================================================
void setup() {
  ledInit();
  Serial.begin(115200);
  delay(150);
  Serial.printf("\n%s FW %s booting...\n", SENSOR_NAME, FW_VERSION);

  loadConfig();

  // DS18B20: 9-bit, non-blocking
  sensors.begin();
  sensors.setResolution(DS_RESOLUTION_BITS);
  sensors.setWaitForConversion(false);
  Serial.printf("DS18B20 sensors found: %d\n", sensors.getDeviceCount());

  // Cache identity strings
  g_chipId       = chipIdHex();
  g_romHex       = ds18b20RomHex();
  g_probeId      = buildProbeId(g_romHex, g_chipId);
  g_instanceName = String(SENSOR_NAME) + "-" + g_chipId.substring(4);
  Serial.printf("Probe ID:  %s\n", g_probeId.c_str());

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
      Serial.printf("[Buffer] Pending from previous session: ~%u readings "
                    "(%u KB)\n", (sz - pos) / 50, (sz - pos) / 1024);
    }
  }

  WiFi.mode(WIFI_STA);
  wm.setConnectTimeout(20);
  wm.setConfigPortalTimeout(0);
  wm.setHostname(SENSOR_NAME);

  // Register parameters exactly once
  wm.addParameter(&p_server);
  wm.addParameter(&p_token);
  wm.addParameter(&p_interval);

  if (!wm.autoConnect(SENSOR_NAME)) {
    Serial.println("[WiFi] No known network; opening portal.");
    p_server.setValue(cfg_server_url.c_str(), cfg_server_url.length());
    p_token.setValue (cfg_token.c_str(),      cfg_token.length());
    char ibuf[12];
    snprintf(ibuf, sizeof(ibuf), "%lu", (unsigned long)cfg_interval);
    p_interval.setValue(ibuf, strlen(ibuf));
    startConfigPortal();
  }

  Serial.print("[WiFi] Connected. IP: ");
  Serial.println(WiFi.localIP());
  g_wasConnected = true;

  syncTime();         // NTP sync — ESP32 RTC holds time through disconnections
  ledBlink(3, 120, 120);
  mdnsAdvertise();
  setupOTA();

  // Flush any readings buffered during a previous session (e.g. power cycle
  // while away from the hub)
  bufferFlush();

  http.on("/",          HTTP_GET,     handleRoot);
  http.on("/whoami",    HTTP_GET,     handleWhoAmI);
  http.on("/status",    HTTP_GET,     handleStatus);
  http.on("/provision", HTTP_POST,    handleProvision);
  http.on("/provision", HTTP_OPTIONS, handleOptions);
  http.begin();
}

// ============================================================================
void loop() {
  http.handleClient();
  ArduinoOTA.handle();

  unsigned long now       = millis();
  bool          connected = (WiFi.status() == WL_CONNECTED);

  // ── WiFi watchdog ─────────────────────────────────────────────────────────
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
    // Just reconnected
    Serial.print("[WiFi] Reconnected. IP: ");
    Serial.println(WiFi.localIP());
    g_wasConnected = true;
    if (!g_timeValid) syncTime();   // get time if we never had it
    mdnsAdvertise();
    bufferFlush();   // upload all offline readings before resuming live posts
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
      return;
    }

    float  tF = DallasTemperature::toFahrenheit(tC);
    String ts = nowIso();   // "" if NTP hasn't synced yet
    g_lastC    = tC;
    g_lastAtMs = now;

    if (connected && ts.length() > 0) {
      // Online and time is known — try a live POST first
      if (postWithTimestamp(ts, tC, tF, g_probeId)) {
        ledOn(); delay(20); ledOff();
        return;
      }
      // POST failed (hub unreachable?) — fall through to buffer
      Serial.println("[POST] Failed — buffering reading.");
    }

    // Offline OR post failed: store to flash (requires valid time)
    // If time is not yet known (very first boot, NTP never synced), the
    // reading is discarded — this only affects the first few seconds of
    // operation before a successful NTP sync.
    bufferAppend(ts, tC, tF);
    ledBlink(2, 80, 120);
  }
}
