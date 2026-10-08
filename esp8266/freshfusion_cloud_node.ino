#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClientSecure.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <WiFiManager.h>

// FreshFusion cloud backend. No laptop/server setup is required after flashing.
static const char* API_URL =
  "https://freshfusion-backend-production.up.railway.app/api/v1/sensors/readings";

#define MOISTURE_PIN A0
#define GREEN_LED D5
#define RED_LED D6
#define SDA_PIN D2
#define SCL_PIN D1

LiquidCrystal_I2C lcd(0x27, 16, 2);
WiFiManager wifiManager;

const unsigned long SEND_INTERVAL_MS = 7000;
const unsigned long WIFI_RETRY_MS = 5000;
unsigned long lastSendAt = 0;
unsigned long lastWiFiRetryAt = 0;

// Calibrate these once against your actual moisture probe.
// Typical resistive/capacitive modules vary substantially.
int DRY_VALUE = 850;
int WET_VALUE = 350;

String deviceId;

void setStatus(bool ok) {
  digitalWrite(GREEN_LED, ok ? HIGH : LOW);
  digitalWrite(RED_LED, ok ? LOW : HIGH);
}

void showLine(uint8_t row, const String& text) {
  lcd.setCursor(0, row);
  String padded = text;
  while (padded.length() < 16) padded += " ";
  lcd.print(padded.substring(0, 16));
}

int readMoistureRaw() {
  return analogRead(MOISTURE_PIN);
}

int moisturePercentFromRaw(int raw) {
  int pct = map(raw, DRY_VALUE, WET_VALUE, 0, 100);
  return constrain(pct, 0, 100);
}

void showSetupPortal() {
  lcd.clear();
  showLine(0, "WiFi Setup Mode");
  showLine(1, "FreshFusion-Setup");
  setStatus(false);
}

bool ensureWiFi() {
  if (WiFi.status() == WL_CONNECTED) return true;

  unsigned long now = millis();
  if (now - lastWiFiRetryAt < WIFI_RETRY_MS) return false;
  lastWiFiRetryAt = now;

  WiFi.reconnect();
  unsigned long started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < 6000) {
    delay(250);
    yield();
  }
  return WiFi.status() == WL_CONNECTED;
}

bool postReading(int raw, int moisture) {
  if (!ensureWiFi()) return false;

  WiFiClientSecure client;
  // Prototype/demo choice: HTTPS transport without certificate pinning avoids
  // future Railway certificate rotations requiring another firmware flash.
  client.setInsecure();

  HTTPClient https;
  if (!https.begin(client, API_URL)) return false;

  https.setTimeout(10000);
  https.addHeader("Content-Type", "application/json");

  String payload = "{";
  payload += "\"device_id\":\"" + deviceId + "\",";
  payload += "\"source\":\"hardware\",";
  payload += "\"moisture\":" + String(moisture) + ",";
  payload += "\"rssi\":" + String(WiFi.RSSI()) + ",";
  payload += "\"uptime_ms\":" + String(millis()) + ",";
  payload += "\"extra_metrics\":{";
  payload += "\"board\":\"ESP8266\",";
  payload += "\"sensor\":\"moisture\",";
  payload += "\"raw_adc\":" + String(raw) + ",";
  payload += "\"firmware\":\"cloud-v1\"";
  payload += "}}";

  int code = https.POST(payload);
  String body = code > 0 ? https.getString() : "";
  https.end();

  Serial.printf("POST %d | moisture=%d%% | raw=%d | RSSI=%d\n",
                code, moisture, raw, WiFi.RSSI());
  if (body.length()) Serial.println(body);

  return code >= 200 && code < 300;
}

void setup() {
  Serial.begin(115200);
  pinMode(GREEN_LED, OUTPUT);
  pinMode(RED_LED, OUTPUT);
  setStatus(false);

  Wire.begin(SDA_PIN, SCL_PIN);
  lcd.init();
  lcd.backlight();
  showLine(0, "FreshFusion Cloud");
  showLine(1, "Starting...");

  deviceId = "FRESHFUSION_" + String(ESP.getChipId(), HEX);
  deviceId.toUpperCase();

  WiFi.mode(WIFI_STA);
  wifiManager.setConfigPortalTimeout(180);
  wifiManager.setConnectTimeout(20);
  wifiManager.setAPCallback([](WiFiManager*) { showSetupPortal(); });

  // Saved credentials are tried automatically. If they fail, the node creates
  // FreshFusion-Setup; connect to it from any phone and select the new Wi-Fi.
  bool connected = wifiManager.autoConnect("FreshFusion-Setup");
  if (!connected) {
    showLine(0, "WiFi not set");
    showLine(1, "Restart to setup");
    setStatus(false);
  } else {
    showLine(0, "WiFi Connected");
    showLine(1, WiFi.localIP().toString());
    setStatus(true);
  }
  delay(1500);
}

void loop() {
  int raw = readMoistureRaw();
  int moisture = moisturePercentFromRaw(raw);

  bool wifiOk = ensureWiFi();
  showLine(0, "Moisture: " + String(moisture) + "%");
  showLine(1, wifiOk ? "Cloud: syncing" : "WiFi: offline");

  unsigned long now = millis();
  if (now - lastSendAt >= SEND_INTERVAL_MS) {
    lastSendAt = now;
    bool sent = postReading(raw, moisture);
    setStatus(sent);
    showLine(1, sent ? "Cloud: ONLINE" : "Cloud: RETRY");
  }

  delay(300);
  yield();
}
