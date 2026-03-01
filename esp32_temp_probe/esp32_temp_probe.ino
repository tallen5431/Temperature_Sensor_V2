// ESP32 + DS18B20 + WiFiManager + mDNS (probe) + OTA + tiny WebServer
// Advertises _temps-probe._tcp and supports /provision + /whoami + /status
//
// Requires (Library Manager):
//   - WiFiManager by tzapu
//   - ArduinoJson  (v6 or v7)
//   - DallasTemperature + OneWire
//   - ArduinoOTA (bundled with ESP32 Arduino core)

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
static const char* FW_VERSION  = "1.3.0";

// ---------------- DS18B20 ---------------------------------------------------
OneWire          oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

// 9-bit resolution gives ~94 ms conversion time (vs 750 ms at 12-bit).
// With setWaitForConversion(false) the loop never blocks waiting for the ADC.
static const uint8_t  DS_RESOLUTION_BITS = 9;
static const uint16_t DS_CONV_MS         = 94;

// ---------------- Config (NVS) ----------------------------------------------
Preferences prefs;  // namespace: "tscfg"
String   cfg_server_url = "";   // e.g. http://<hub>:8088/api/ingest
String   cfg_token      = "";
uint32_t cfg_interval   = 5000; // ms between readings

// ---------------- WiFiManager parameters ------------------------------------
WiFiManager wm;
WiFiManagerParameter p_server  ("server",   "Server URL",                   "",     128);
WiFiManagerParameter p_token   ("token",    "Ingest token (optional)",      "",      64);
WiFiManagerParameter p_interval("interval", "Read interval (ms)",           "5000",  10);

// ---------------- HTTP server -----------------------------------------------
WebServer http(80);

// ---------------- Cached identity (computed once in setup) ------------------
static String g_chipId;        // lower 32-bit of MAC as 8 hex chars
static String g_romHex;        // DS18B20 ROM as 16 hex chars
static String g_probeId;       // e.g. TempProbe-3F2A
static String g_instanceName;  // e.g. TempSensor-12AB3F2A

// ---------------- State -----------------------------------------------------
static unsigned long g_lastSend    = 0;     // millis() of last conversion request
static unsigned long g_convReqAt   = 0;     // millis() when conversion was requested
static bool          g_convPending = false; // true between request and read
static float         g_lastC       = NAN;   // last valid reading
static unsigned long g_lastAtMs    = 0;     // millis() of last valid reading
static bool          g_wasConnected = false;

// ---------------- Helpers ---------------------------------------------------
String chipIdHex() {
  uint32_t lo = (uint32_t)(ESP.getEfuseMac() & 0xFFFFFFFFULL);
  char buf[9];
  snprintf(buf, sizeof(buf), "%08X", lo);
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

// Stable probe ID derived from DS18B20 ROM tail; falls back to chip MAC tail.
String buildProbeId(const String& rom, const String& chip) {
  if (rom.length() >= 4) return "TempProbe-"  + rom.substring(rom.length() - 4);
  return                        "TempSensor-" + chip.substring(4);
}

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

// ---------------- HTTP helpers ----------------------------------------------
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

void handleOptions() {
  addCORS();
  http.send(204);
}

// ---------------- POST reading to hub ---------------------------------------
bool postReading(float tC) {
  if (WiFi.status() != WL_CONNECTED || cfg_server_url.length() == 0) return false;

  float tF = DallasTemperature::toFahrenheit(tC);

  StaticJsonDocument<256> doc;
  doc["temperature_c"] = tC;
  doc["temperature_f"] = tF;      // FIX: was computed but never sent
  doc["probe_id"]      = g_probeId;

  String body;
  serializeJson(doc, body);

  HTTPClient httpc;
  httpc.begin(cfg_server_url);
  httpc.setTimeout(3000);          // FIX: don't hang if hub is unreachable
  httpc.addHeader("Content-Type", "application/json");
  if (cfg_token.length()) httpc.addHeader("X-Token",    cfg_token);
  httpc.addHeader("X-Probe-ID", g_probeId);

  int code = httpc.POST((uint8_t*)body.c_str(), body.length());
  httpc.end();

  Serial.printf("[POST] %s -> %d (tC=%.2f tF=%.2f id=%s)\n",
    cfg_server_url.c_str(), code, tC, tF, g_probeId.c_str());
  return (code >= 200 && code < 300);
}

// ---------------- mDNS -----------------------------------------------------
// Called once on boot and again after every WiFi reconnection so the hub
// always has the current IP address.
void mdnsAdvertise() {
  MDNS.end();  // safe to call even if not previously started
  String host = g_instanceName;
  host.replace(".", "-");
  if (!MDNS.begin(host.c_str())) {
    Serial.println("[mDNS] init failed");
    return;
  }
  MDNS.addService("_temps-probe", "_tcp", 80);
  MDNS.addServiceTxt("_temps-probe", "_tcp", "id",   g_probeId);
  MDNS.addServiceTxt("_temps-probe", "_tcp", "name", g_instanceName);
  Serial.printf("[mDNS] advertising %s (%s) as _temps-probe._tcp\n",
    g_instanceName.c_str(), host.c_str());
}

// ---------------- WebServer handlers ----------------------------------------
void handleRoot() {
  // Use cached g_probeId — avoids a 1-Wire bus read on every HTTP request
  String html = String("<!doctype html><meta charset='utf-8'>")
    + "<h3>" + SENSOR_NAME + " " + FW_VERSION + "</h3>"
    + "<p>ID: "       + g_probeId      + "</p>"
    + "<p>Server: "   + cfg_server_url + "</p>"
    + "<p>Interval: " + String(cfg_interval) + " ms</p>";
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
  sendJSON(200, doc);
}

void handleStatus() {
  StaticJsonDocument<256> doc;
  doc["id"]          = g_probeId;
  doc["interval_ms"] = cfg_interval;
  doc["server_url"]  = cfg_server_url;
  if (!isnan(g_lastC)) {
    doc["last_c"]  = g_lastC;
    doc["last_ms"] = g_lastAtMs;
  }
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

// ---------------- WiFi portal -----------------------------------------------
void startConfigPortal() {
  uint32_t chip = (uint32_t)ESP.getEfuseMac();
  char apName[32];
  snprintf(apName, sizeof(apName), "%s-%04X", SENSOR_NAME, (uint16_t)(chip & 0xFFFF));

  wm.setClass("invert");
  wm.setTitle(String(SENSOR_NAME) + " (" + FW_VERSION + ")");
  wm.setConfigPortalBlocking(true);
  wm.setParamsPage(true);
  // wm.setTimeout(0) intentionally omitted — already set in setup()

  // Pre-fill form fields with current saved values
  p_server.setValue(cfg_server_url.c_str(), cfg_server_url.length());
  p_token.setValue (cfg_token.c_str(),      cfg_token.length());
  char ibuf[12];
  snprintf(ibuf, sizeof(ibuf), "%lu", (unsigned long)cfg_interval);
  p_interval.setValue(ibuf, strlen(ibuf));

  // FIX: parameters were registered in setup() — do NOT call wm.addParameter
  // again here or they appear twice in the portal form.

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

// ---------------- OTA -------------------------------------------------------
void setupOTA() {
  ArduinoOTA.setHostname(g_instanceName.c_str());
  ArduinoOTA.onStart([]() {
    Serial.println("[OTA] Starting...");
    ledBlink(3, 50, 50);
  });
  ArduinoOTA.onEnd  ([]()              { Serial.println("[OTA] Done."); });
  ArduinoOTA.onError([](ota_error_t e) { Serial.printf("[OTA] Error[%u]\n", e); });
  ArduinoOTA.begin();
  Serial.println("[OTA] Ready — flash over Wi-Fi using Arduino IDE or espota.py");
}

// ============================================================================
void setup() {
  ledInit();
  Serial.begin(115200);
  delay(150);
  Serial.printf("\n%s FW %s booting...\n", SENSOR_NAME, FW_VERSION);

  loadConfig();

  // DS18B20: 9-bit resolution, non-blocking conversion
  sensors.begin();
  sensors.setResolution(DS_RESOLUTION_BITS);
  sensors.setWaitForConversion(false);  // requestTemperatures() returns instantly
  Serial.printf("DS18B20 sensors found: %d\n", sensors.getDeviceCount());

  // Cache identity strings — computed once, reused everywhere
  g_chipId       = chipIdHex();
  g_romHex       = ds18b20RomHex();
  g_probeId      = buildProbeId(g_romHex, g_chipId);
  g_instanceName = String(SENSOR_NAME) + "-" + g_chipId.substring(4);
  Serial.printf("Probe ID:  %s\n", g_probeId.c_str());
  Serial.printf("Instance:  %s\n", g_instanceName.c_str());

  WiFi.mode(WIFI_STA);
  wm.setConnectTimeout(20);
  wm.setConfigPortalTimeout(0);
  wm.setHostname(SENSOR_NAME);

  // FIX: register parameters exactly once — shared by autoConnect portal
  // and startConfigPortal(); duplicate calls caused duplicate form fields.
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
  ledBlink(3, 120, 120);

  mdnsAdvertise();
  setupOTA();

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

  unsigned long now = millis();

  // ── WiFi watchdog ──────────────────────────────────────────────────────────
  bool connected = (WiFi.status() == WL_CONNECTED);

  if (!connected) {
    if (g_wasConnected) {
      Serial.println("[WiFi] Connection lost.");
      g_wasConnected = false;
    }
    // Retry reconnection once every 5 s rather than hammering the stack
    static unsigned long lastReconnAt = 0;
    if (now - lastReconnAt >= 5000) {
      Serial.println("[WiFi] Attempting reconnect...");
      WiFi.reconnect();
      lastReconnAt = now;
    }
    return;  // keep serving HTTP / OTA while offline
  }

  if (!g_wasConnected) {
    // Just reconnected — re-advertise mDNS with the (possibly new) IP
    // so the hub's mDNS browser can find the probe again.
    Serial.print("[WiFi] Reconnected. IP: ");
    Serial.println(WiFi.localIP());
    g_wasConnected = true;
    mdnsAdvertise();
  }

  // ── Phase 1: kick off a conversion ────────────────────────────────────────
  // requestTemperatures() returns immediately (setWaitForConversion(false));
  // the DS18B20 runs its ADC in the background for DS_CONV_MS milliseconds.
  if (!g_convPending && (now - g_lastSend >= cfg_interval)) {
    sensors.requestTemperatures();
    g_convReqAt   = now;
    g_convPending = true;
    g_lastSend    = now;
  }

  // ── Phase 2: read result once conversion window has elapsed ───────────────
  // The web server keeps running during the DS_CONV_MS gap — no blocking here.
  if (g_convPending && (now - g_convReqAt >= DS_CONV_MS)) {
    g_convPending = false;
    float tC = sensors.getTempCByIndex(0);

    if (tC == DEVICE_DISCONNECTED_C) {
      Serial.println("[Temp] Sensor disconnected — reinitialising bus...");
      // Attempt bus recovery rather than waiting for a reboot
      sensors.begin();
      sensors.setResolution(DS_RESOLUTION_BITS);
      sensors.setWaitForConversion(false);
      ledBlink(2, 60, 160);
    } else {
      g_lastC    = tC;
      g_lastAtMs = now;   // FIX: use captured `now`, not a redundant millis() call
      bool ok = postReading(tC);
      if (ok) { ledOn(); delay(20); ledOff(); }
      else    { ledBlink(2, 80, 120); }
    }
  }
}
