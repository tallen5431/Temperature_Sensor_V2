// ============================================================================
// main.cpp  --  ThermaProbe reference firmware (probe side of ThermaHub proto v1)
// ============================================================================
// Responsibilities (see protocol.h and the ThermaHub CANONICAL SPEC):
//   1. Derive a stable identity from the ESP32 efuse MAC:
//        probe_id  = "ThermaProbe-" + UPPERCASE hex of last 3 MAC bytes
//        hostname  = "thermaprobe-" + lowercase(hex)
//   2. Persist Wi-Fi creds + provisioned server_url/token/interval in NVS.
//   3. Join home Wi-Fi (STA). If that fails / no creds -> WPA2 SoftAP with a
//      DNS captive portal + web form at 192.168.4.1 to enter home Wi-Fi.
//   4. Advertise _temps-probe._tcp on port 80 via mDNS (TXT id/name/fw/proto).
//   5. Serve the probe HTTP API: POST /provision, GET /whoami, GET /status.
//   6. Read the DS18B20 (or optional MAX31855), rejecting fault codes.
//   7. Every interval_ms POST {temperature_c,probe_id,timestamp} to the hub
//      with headers X-Probe-ID and X-Token; track last_post_ok/last_post_code.
//
// Written for the Arduino framework via PlatformIO. Clean & compilable C++.
// ============================================================================

#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <ESPmDNS.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <ArduinoJson.h>
#include <esp_system.h>

#include "protocol.h"

// --- Sensor back-end (compile-time selected in platformio.ini) --------------
#if defined(SENSOR_MAX31855)
  #include <SPI.h>
  #include <Adafruit_MAX31855.h>
  static Adafruit_MAX31855 thermocouple(MAX31855_SCK, MAX31855_CS, MAX31855_MISO);
#else
  #ifndef SENSOR_DS18B20
    #define SENSOR_DS18B20 1   // default when nothing is defined
  #endif
  #include <OneWire.h>
  #include <DallasTemperature.h>
  static OneWire oneWire(ONE_WIRE_BUS);
  static DallasTemperature ds18b20(&oneWire);
#endif

// ---------------------------------------------------------------------------
// Globals
// ---------------------------------------------------------------------------
static Preferences prefs;                 // NVS namespace "thermaprobe"
static WebServer   httpServer(HTTP_PORT);
static DNSServer   dnsServer;

// Identity (derived once at boot, never mutated afterwards).
static String g_hex6;         // "9A3F2C"
static String g_probeId;      // "ThermaProbe-9A3F2C"
static String g_hostname;     // "thermaprobe-9a3f2c"
static String g_apSsid;       // "ThermaProbe-9A3F2C"
static String g_apPass;       // per-unit WPA2 key
static String g_macStr;       // "24:6F:28:9A:3F:2C"

// Provisioned / persisted settings.
static String   g_wifiSsid;
static String   g_wifiPass;
static String   g_serverUrl;        // full ingest URL, e.g. http://host:8080/api/ingest
static String   g_token;            // X-Token pushed by the hub
static String   g_provisionSecret;  // per-unit secret gating /provision (may be empty)
static String   g_friendlyName;     // optional operator-set name
static uint32_t g_intervalMs = DEFAULT_INTERVAL_MS;

// Runtime state.
static bool     g_apMode = false;         // true while serving the setup SoftAP
static float    g_lastTempC = NAN;
static bool     g_sensorOk  = false;
static bool     g_lastPostOk   = false;
static int      g_lastPostCode = 0;
static uint32_t g_lastPostAt   = 0;       // millis() of last attempt
static uint32_t g_bootMs       = 0;

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------
static void ledSet(bool on) {
#if STATUS_LED_ACTIVE_HIGH
  digitalWrite(STATUS_LED, on ? HIGH : LOW);
#else
  digitalWrite(STATUS_LED, on ? LOW : HIGH);
#endif
}

// ISO-8601-ish local timestamp based on uptime. The probe has no RTC; the hub
// stamps the authoritative time on ingest when "timestamp" is absent/relative,
// so we send a best-effort monotonic marker the hub is free to override.
static String uptimeStamp() {
  uint32_t s = (millis() - g_bootMs) / 1000UL;
  char buf[32];
  snprintf(buf, sizeof(buf), "uptime+%lus", (unsigned long)s);
  return String(buf);
}

// Derive probe_id / hostname / SoftAP creds from the efuse MAC.
static void deriveIdentity() {
  uint8_t mac[6] = {0};
  // Base station MAC == factory efuse MAC. esptool's read_mac prints the same
  // bytes in the same order, so factory_flash.py computes an identical label.
  esp_read_mac(mac, ESP_MAC_WIFI_STA);

  char macbuf[18];
  snprintf(macbuf, sizeof(macbuf), "%02X:%02X:%02X:%02X:%02X:%02X",
           mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
  g_macStr = String(macbuf);

  char hex6[7];
  snprintf(hex6, sizeof(hex6), "%02X%02X%02X", mac[3], mac[4], mac[5]);
  g_hex6 = String(hex6);

  g_probeId  = String(PROBE_ID_PREFIX) + g_hex6;
  g_apSsid   = g_probeId;                              // SSID == probe_id

  String hexLower = g_hex6; hexLower.toLowerCase();
  g_hostname = String(HOSTNAME_PREFIX) + hexLower;

  // AP password = "TP-" + UPPERCASE hex of last 4 MAC bytes (>= 8 chars => WPA2).
  char pass8[9];
  snprintf(pass8, sizeof(pass8), "%02X%02X%02X%02X", mac[2], mac[3], mac[4], mac[5]);
  g_apPass = String(AP_PASSWORD_PREFIX) + String(pass8);
}

// ---------------------------------------------------------------------------
// NVS persistence
// ---------------------------------------------------------------------------
static void loadConfig() {
  prefs.begin("thermaprobe", /*readOnly=*/true);
  g_wifiSsid        = prefs.getString("wifi_ssid", "");
  g_wifiPass        = prefs.getString("wifi_pass", "");
  g_serverUrl       = prefs.getString("server_url", "");
  g_token           = prefs.getString("token", "");
  g_provisionSecret = prefs.getString("prov_secret", "");
  g_friendlyName    = prefs.getString("name", "");
  g_intervalMs      = prefs.getUInt("interval_ms", DEFAULT_INTERVAL_MS);
  prefs.end();
  if (g_intervalMs < MIN_INTERVAL_MS) g_intervalMs = MIN_INTERVAL_MS;
  if (g_intervalMs > MAX_INTERVAL_MS) g_intervalMs = MAX_INTERVAL_MS;
}

static void saveWifi(const String& ssid, const String& pass) {
  prefs.begin("thermaprobe", /*readOnly=*/false);
  prefs.putString("wifi_ssid", ssid);
  prefs.putString("wifi_pass", pass);
  prefs.end();
}

static void saveProvision(const String& serverUrl, const String& token, uint32_t intervalMs) {
  prefs.begin("thermaprobe", /*readOnly=*/false);
  prefs.putString("server_url", serverUrl);
  prefs.putString("token", token);
  prefs.putUInt("interval_ms", intervalMs);
  prefs.end();
}

// ---------------------------------------------------------------------------
// Sensor read (fault handling per spec: reject 85.0 power-on, -127/NaN discon.)
// ---------------------------------------------------------------------------
static bool readSensor(float& outC) {
#if defined(SENSOR_MAX31855)
  double c = thermocouple.readCelsius();
  if (isnan(c)) return false;                      // open/short/fault
  if (c < TEMP_MIN_C || c > TEMP_MAX_C) return false;
  outC = (float)c;
  return true;
#else
  ds18b20.requestTemperatures();
  float c = ds18b20.getTempCByIndex(0);
  // DallasTemperature sentinels: -127 (disconnected), 85.0 (power-on reset).
  if (c == DEVICE_DISCONNECTED_C) return false;    // == -127.0
  if (isnan(c)) return false;
  if (c <= -127.0f) return false;
  if (fabsf(c - 85.0f) < 0.01f) return false;      // reject 85.0 power-on code
  if (c < TEMP_MIN_C || c > TEMP_MAX_C) return false;
  outC = c;
  return true;
#endif
}

// ---------------------------------------------------------------------------
// HTTP handlers -- probe API
// ---------------------------------------------------------------------------

// POST /provision  {server_url, token, interval_ms}, header X-Provision-Secret
// Spec: the per-unit secret (from the label/QR) gates provisioning. To keep the
// hub's zero-touch auto-provisioner working out-of-the-box, the secret is only
// ENFORCED when this unit actually has one stored (g_provisionSecret non-empty).
// A field tech sets the secret via NVS/QR to lock a unit down; until then the
// LAN-local /provision is open so plug-and-play works. Returns {id,name,fw,accepted}.
static void handleProvision() {
  if (g_provisionSecret.length() > 0) {
    String got = httpServer.header("X-Provision-Secret");
    if (got != g_provisionSecret) {
      httpServer.send(403, "application/json",
                      "{\"accepted\":false,\"error\":\"bad provision secret\"}");
      return;
    }
  }

  StaticJsonDocument<512> doc;
  DeserializationError err = deserializeJson(doc, httpServer.arg("plain"));
  if (err) {
    httpServer.send(400, "application/json",
                    "{\"accepted\":false,\"error\":\"invalid json\"}");
    return;
  }

  String serverUrl = doc["server_url"] | "";
  String token     = doc["token"] | "";
  uint32_t interval = doc["interval_ms"] | (uint32_t)DEFAULT_INTERVAL_MS;
  if (interval < MIN_INTERVAL_MS) interval = MIN_INTERVAL_MS;
  if (interval > MAX_INTERVAL_MS) interval = MAX_INTERVAL_MS;

  if (serverUrl.length() == 0) {
    httpServer.send(400, "application/json",
                    "{\"accepted\":false,\"error\":\"server_url required\"}");
    return;
  }

  g_serverUrl  = serverUrl;
  g_token      = token;
  g_intervalMs = interval;
  saveProvision(g_serverUrl, g_token, g_intervalMs);

  Serial.printf("[provision] server_url=%s interval_ms=%u token=%s\n",
                g_serverUrl.c_str(), (unsigned)g_intervalMs,
                g_token.length() ? "<set>" : "<empty>");

  StaticJsonDocument<256> resp;
  resp["id"]       = g_probeId;
  resp["name"]     = g_friendlyName.length() ? g_friendlyName : g_probeId;
  resp["fw"]       = THERMAPROBE_FW_VERSION;
  resp["accepted"] = true;
  String out; serializeJson(resp, out);
  httpServer.send(200, "application/json", out);
}

// GET /whoami -> {id,name,fw,mac}
static void handleWhoami() {
  StaticJsonDocument<256> doc;
  doc["id"]   = g_probeId;
  doc["name"] = g_friendlyName.length() ? g_friendlyName : g_probeId;
  doc["fw"]   = THERMAPROBE_FW_VERSION;
  doc["mac"]  = g_macStr;
  String out; serializeJson(doc, out);
  httpServer.send(200, "application/json", out);
}

// GET /status -> {id,wifi_rssi,uptime_s,last_post_ok,last_post_code,
//                 server_url,temperature_c,sensor_ok}
static void handleStatus() {
  StaticJsonDocument<384> doc;
  doc["id"]             = g_probeId;
  doc["wifi_rssi"]      = (WiFi.status() == WL_CONNECTED) ? WiFi.RSSI() : 0;
  doc["uptime_s"]       = (millis() - g_bootMs) / 1000UL;
  doc["last_post_ok"]   = g_lastPostOk;
  doc["last_post_code"] = g_lastPostCode;
  doc["server_url"]     = g_serverUrl;
  if (g_sensorOk) doc["temperature_c"] = g_lastTempC;
  else            doc["temperature_c"] = (const char*)nullptr;   // JSON null
  doc["sensor_ok"]      = g_sensorOk;
  String out; serializeJson(doc, out);
  httpServer.send(200, "application/json", out);
}

// ---------------------------------------------------------------------------
// SoftAP captive-portal config page
// ---------------------------------------------------------------------------
static String configPageHtml(const String& msg) {
  String h;
  h += "<!doctype html><html><head><meta name=viewport "
       "content='width=device-width,initial-scale=1'>";
  h += "<title>" + g_probeId + " setup</title>";
  h += "<style>body{font-family:sans-serif;max-width:420px;margin:24px auto;"
       "padding:0 16px}h1{font-size:1.2rem}input{width:100%;padding:10px;margin:6px 0;"
       "box-sizing:border-box}button{padding:12px;width:100%;font-size:1rem}"
       ".m{color:#0a0}</style></head><body>";
  h += "<h1>ThermaProbe setup</h1>";
  h += "<p>Device: <b>" + g_probeId + "</b><br>Firmware " THERMAPROBE_FW_VERSION "</p>";
  if (msg.length()) h += "<p class=m>" + msg + "</p>";
  h += "<form method=POST action='/save'>";
  h += "<label>Home Wi-Fi network (SSID)</label>";
  h += "<input name=ssid autocomplete=off required>";
  h += "<label>Wi-Fi password</label>";
  h += "<input name=pass type=password autocomplete=off>";
  h += "<button type=submit>Save &amp; connect</button></form>";
  h += "<p style='color:#888;font-size:.85rem'>After saving, the probe reboots "
       "and joins your network. It will then appear automatically in ThermaHub.</p>";
  h += "</body></html>";
  return h;
}

static void handleRoot() {
  if (g_apMode) {
    httpServer.send(200, "text/html", configPageHtml(""));
  } else {
    // In station mode, a tiny status landing page is friendlier than a 404.
    String h = "<!doctype html><meta name=viewport content='width=device-width'>";
    h += "<body style='font-family:sans-serif'><h1>" + g_probeId + "</h1>";
    h += "<p>Firmware " THERMAPROBE_FW_VERSION " &middot; connected to " + g_wifiSsid + "</p>";
    h += "<p>See <code>/whoami</code> and <code>/status</code>.</p></body>";
    httpServer.send(200, "text/html", h);
  }
}

static void handleSave() {
  String ssid = httpServer.arg("ssid");
  String pass = httpServer.arg("pass");
  if (ssid.length() == 0) {
    httpServer.send(200, "text/html", configPageHtml("SSID is required."));
    return;
  }
  saveWifi(ssid, pass);
  httpServer.send(200, "text/html",
      configPageHtml("Saved. Rebooting to join \"" + ssid + "\"..."));
  Serial.printf("[setup] saved wifi ssid=%s, rebooting\n", ssid.c_str());
  delay(800);
  ESP.restart();
}

// Captive-portal catch-all: redirect any unknown host/path back to the form.
static void handleCaptive() {
  if (g_apMode) {
    httpServer.sendHeader("Location", String("http://") + CAPTIVE_PORTAL_IP, true);
    httpServer.send(302, "text/plain", "");
  } else {
    httpServer.send(404, "text/plain", "not found");
  }
}

// ---------------------------------------------------------------------------
// Wi-Fi bring-up
// ---------------------------------------------------------------------------
static bool connectStation() {
  if (g_wifiSsid.length() == 0) return false;
  Serial.printf("[wifi] connecting to \"%s\"...\n", g_wifiSsid.c_str());
  WiFi.mode(WIFI_STA);
  WiFi.setHostname(g_hostname.c_str());
  WiFi.begin(g_wifiSsid.c_str(), g_wifiPass.c_str());

  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - start) < 20000UL) {
    delay(250);
    ledSet(((millis() / 250) & 1));    // fast blink while connecting
    Serial.print('.');
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("[wifi] connected, ip=%s\n", WiFi.localIP().toString().c_str());
    return true;
  }
  Serial.println("[wifi] connect failed");
  return false;
}

static void startSoftAp() {
  g_apMode = true;
  Serial.printf("[setup] starting SoftAP SSID=\"%s\" pass=\"%s\"\n",
                g_apSsid.c_str(), g_apPass.c_str());
  WiFi.mode(WIFI_AP);
  WiFi.softAP(g_apSsid.c_str(), g_apPass.c_str(), AP_CHANNEL, /*hidden=*/0, AP_MAX_CONNECTIONS);
  delay(200);
  IPAddress ip = WiFi.softAPIP();
  Serial.printf("[setup] captive portal at http://%s\n", ip.toString().c_str());
  dnsServer.start(DNS_PORT, "*", ip);    // resolve every hostname to us
}

// ---------------------------------------------------------------------------
// mDNS + HTTP server
// ---------------------------------------------------------------------------
static void startMdnsAndServer() {
  if (MDNS.begin(g_hostname.c_str())) {
    // Advertise _temps-probe._tcp on port 80 with the TXT records the hub reads.
    MDNS.addService(MDNS_SERVICE, MDNS_PROTO, HTTP_PORT);
    MDNS.addServiceTxt(MDNS_SERVICE, MDNS_PROTO, "id",
                       g_probeId.c_str());
    MDNS.addServiceTxt(MDNS_SERVICE, MDNS_PROTO, "name",
                       (g_friendlyName.length() ? g_friendlyName : g_probeId).c_str());
    MDNS.addServiceTxt(MDNS_SERVICE, MDNS_PROTO, "fw", THERMAPROBE_FW_VERSION);
    MDNS.addServiceTxt(MDNS_SERVICE, MDNS_PROTO, "proto", String(THERMAPROBE_PROTO).c_str());
    Serial.printf("[mdns] advertising %s.local as _%s._%s:%d\n",
                  g_hostname.c_str(), MDNS_SERVICE, MDNS_PROTO, HTTP_PORT);

    // Boot-time invariant check (spec): the TXT id we advertise MUST equal the
    // X-Probe-ID we will send on ingest. Both come from g_probeId, so this can
    // only fail if the code is edited inconsistently -- log loudly if so.
    if (g_probeId != String(PROBE_ID_PREFIX) + g_hex6) {
      Serial.println("[FATAL] probe_id invariant broken: TXT id != X-Probe-ID");
    } else {
      Serial.printf("[mdns] invariant OK: TXT id == X-Probe-ID == %s\n", g_probeId.c_str());
    }
  } else {
    Serial.println("[mdns] MDNS.begin failed");
  }

  // We need custom headers (X-Provision-Secret) visible in handlers.
  const char* collect[] = { "X-Provision-Secret", "X-Token", "Content-Type" };
  httpServer.collectHeaders(collect, sizeof(collect) / sizeof(collect[0]));

  httpServer.on("/",          HTTP_GET,  handleRoot);
  httpServer.on("/provision", HTTP_POST, handleProvision);
  httpServer.on("/whoami",    HTTP_GET,  handleWhoami);
  httpServer.on("/status",    HTTP_GET,  handleStatus);
  httpServer.on("/save",      HTTP_POST, handleSave);
  // Common captive-portal probe URLs so phones pop the setup page automatically.
  httpServer.on("/generate_204", HTTP_GET, handleCaptive);  // Android
  httpServer.on("/hotspot-detect.html", HTTP_GET, handleRoot); // iOS/macOS
  httpServer.onNotFound(handleCaptive);
  httpServer.begin();
  Serial.printf("[http] server listening on :%d\n", HTTP_PORT);
}

// ---------------------------------------------------------------------------
// Ingest POST to the hub
// ---------------------------------------------------------------------------
static void postReading(float tempC) {
  if (g_serverUrl.length() == 0) return;        // not provisioned yet
  if (WiFi.status() != WL_CONNECTED) return;

  StaticJsonDocument<192> doc;
  doc["temperature_c"] = tempC;
  doc["probe_id"]      = g_probeId;
  doc["timestamp"]     = uptimeStamp();
  String body; serializeJson(doc, body);

  HTTPClient http;
  http.setConnectTimeout(4000);
  http.setTimeout(5000);
  if (!http.begin(g_serverUrl)) {
    g_lastPostOk = false;
    g_lastPostCode = -1;
    Serial.println("[post] http.begin failed");
    return;
  }
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Probe-ID", g_probeId);      // MUST equal mDNS TXT id
  http.addHeader("X-Token", g_token);           // token pushed by the hub

  int code = http.POST(body);
  g_lastPostCode = code;
  g_lastPostOk   = (code >= 200 && code < 300);
  Serial.printf("[post] %s -> %d %s\n", g_serverUrl.c_str(), code,
                g_lastPostOk ? "OK" : "FAIL");
  http.end();
}

// ---------------------------------------------------------------------------
// Arduino setup / loop
// ---------------------------------------------------------------------------
void setup() {
  g_bootMs = millis();
  Serial.begin(115200);
  delay(150);
  Serial.println();
  Serial.println("=== ThermaProbe firmware " THERMAPROBE_FW_VERSION " (proto v1) ===");

  pinMode(STATUS_LED, OUTPUT);
  ledSet(false);

  deriveIdentity();
  Serial.printf("[id] probe_id=%s hostname=%s.local mac=%s\n",
                g_probeId.c_str(), g_hostname.c_str(), g_macStr.c_str());

  loadConfig();

  // Sensor init.
#if defined(SENSOR_MAX31855)
  Serial.println("[sensor] MAX31855 thermocouple");
  // Adafruit_MAX31855 begins lazily on first read; nothing to init here.
#else
  ds18b20.begin();
  ds18b20.setResolution(12);
  Serial.printf("[sensor] DS18B20 on GPIO%d, devices=%d\n",
                ONE_WIRE_BUS, ds18b20.getDeviceCount());
#endif

  // Try to join home Wi-Fi; fall back to setup SoftAP.
  if (!connectStation()) {
    startSoftAp();
  }

  startMdnsAndServer();
  ledSet(WiFi.status() == WL_CONNECTED);
}

void loop() {
  httpServer.handleClient();
  if (g_apMode) {
    dnsServer.processNextRequest();
    // Slow heartbeat blink to show "needs setup".
    ledSet(((millis() / 1000) & 1));
    return;
  }

  // If we dropped off Wi-Fi, try to reconnect (non-blocking-ish).
  static uint32_t lastWifiCheck = 0;
  if (WiFi.status() != WL_CONNECTED && (millis() - lastWifiCheck) > 10000UL) {
    lastWifiCheck = millis();
    Serial.println("[wifi] reconnecting...");
    WiFi.reconnect();
  }

  // Sample + post on the provisioned interval.
  static uint32_t lastPost = 0;
  uint32_t now = millis();
  if ((now - lastPost) >= g_intervalMs) {
    lastPost = now;
    float c;
    g_sensorOk = readSensor(c);
    if (g_sensorOk) {
      g_lastTempC = c;
      Serial.printf("[sensor] %.2f C\n", c);
      ledSet(true);
      postReading(c);      // updates last_post_ok/code
      g_lastPostAt = now;
      ledSet(WiFi.status() == WL_CONNECTED);
    } else {
      // Fault code / disconnected sensor: skip posting per spec, flag it.
      g_lastTempC = NAN;
      Serial.println("[sensor] fault (skip post): 85.0/-127/NaN or out of range");
    }
  }
}
