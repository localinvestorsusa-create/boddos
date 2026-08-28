/*
 * BODDOS ESP32 sensor node.
 *
 * Scans real, physically-available signals and POSTs them to your BODDOS node:
 *   - Wi-Fi access points in range (BSSID/SSID/RSSI)  -> nearby-device sense
 *   - BLE advertisers in range (MAC/name/RSSI)        -> tracker detection
 *   - (optional) magnetometer magnitude               -> metal / field anomaly
 *   - (optional) mic level, motion                    -> ambient awareness
 *
 * This is honest hardware: RSSI gives coarse "closer/farther", not identity or
 * precise distance, and there is no through-wall imaging or remote vitals.
 *
 * Build: Arduino IDE / arduino-cli with the ESP32 board package.
 * Libraries: WiFi, HTTPClient (bundled), BLEDevice (ESP32 BLE Arduino).
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <BLEDevice.h>
#include <BLEScan.h>
#include <BLEAdvertisedDevice.h>

// ------------------ CONFIG: edit these ------------------
const char* WIFI_SSID   = "YOUR_WIFI";
const char* WIFI_PASS   = "YOUR_WIFI_PASSWORD";
const char* NODE_URL    = "http://192.168.1.10:8787/api/sensors/ingest"; // MacBook node
const char* SENSOR_ID   = "esp32-pocket";
const int   SCAN_PERIOD_MS = 5000;
const int   BLE_SCAN_SECONDS = 3;
// --------------------------------------------------------

BLEScan* bleScan;

void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("WiFi");
  while (WiFi.status() != WL_CONNECTED) { delay(400); Serial.print("."); }
  Serial.printf(" connected: %s\n", WiFi.localIP().toString().c_str());
}

String scanWifiJson() {
  int n = WiFi.scanNetworks(false, true);
  String out = "[";
  for (int i = 0; i < n && i < 20; i++) {
    if (i) out += ",";
    out += "{\"bssid\":\"" + WiFi.BSSIDstr(i) + "\",";
    out += "\"ssid\":\"" + WiFi.SSID(i) + "\",";
    out += "\"rssi\":" + String(WiFi.RSSI(i)) + "}";
  }
  out += "]";
  WiFi.scanDelete();
  return out;
}

String scanBleJson() {
  BLEScanResults results = bleScan->start(BLE_SCAN_SECONDS, false);
  String out = "[";
  int count = results.getCount();
  for (int i = 0; i < count && i < 30; i++) {
    BLEAdvertisedDevice d = results.getDevice(i);
    if (i) out += ",";
    out += "{\"mac\":\"" + String(d.getAddress().toString().c_str()) + "\",";
    String name = d.haveName() ? String(d.getName().c_str()) : "";
    name.replace("\"", "'");
    out += "\"name\":\"" + name + "\",";
    out += "\"rssi\":" + String(d.getRSSI()) + "}";
  }
  out += "]";
  bleScan->clearResults();
  return out;
}

void postReadings(const String& wifi, const String& ble) {
  if (WiFi.status() != WL_CONNECTED) connectWifi();
  HTTPClient http;
  http.begin(NODE_URL);
  http.addHeader("Content-Type", "application/json");
  // Add mag_uT / sound_db / motion / lat / lon here if you wire those sensors.
  String body = "{\"source\":\"" + String(SENSOR_ID) + "\",";
  body += "\"wifi\":" + wifi + ",\"ble\":" + ble + "}";
  int code = http.POST(body);
  Serial.printf("POST %d\n", code);
  http.end();
}

void setup() {
  Serial.begin(115200);
  delay(200);
  connectWifi();
  BLEDevice::init("");
  bleScan = BLEDevice::getScan();
  bleScan->setActiveScan(true);
  bleScan->setInterval(100);
  bleScan->setWindow(99);
}

void loop() {
  String wifi = scanWifiJson();
  String ble = scanBleJson();
  postReadings(wifi, ble);
  delay(SCAN_PERIOD_MS);
}
