# BODDOS ESP32 sensor node

Flash this to an ESP32 (with BLE — e.g. ESP32-WROOM/WROVER, ESP32-S3). It scans
Wi-Fi and BLE around you and POSTs the readings to your BODDOS node, feeding the
awareness view and the tracker-detection safety module.

## What it senses (honestly)

- **Wi-Fi APs in range** — count + coarse proximity from RSSI.
- **BLE advertisers** — the raw material for "is a tracker following me?".
- **Optional add-ons** (wire your own): magnetometer (QMC5883/HMC5883) for
  metal/field anomalies, a mic module for ambient sound level, an IMU for
  motion. Fill the extra JSON fields in `postReadings()`.

It does **not** and cannot: see through walls, image people, or read anyone's
vitals. RSSI is coarse distance only.

## Flash it

1. Install the ESP32 board package (Arduino IDE Boards Manager, or `arduino-cli`).
2. Install the **ESP32 BLE Arduino** library.
3. Edit the CONFIG block at the top of `boddos_sensor.ino`:
   - `WIFI_SSID` / `WIFI_PASS`
   - `NODE_URL` → your MacBook node, e.g. `http://192.168.1.10:8787/api/sensors/ingest`
   - `SENSOR_ID` → a name for this node, e.g. `esp32-pocket`
4. Select your board + port, Upload.
5. Open Serial Monitor at 115200 to watch `POST 200` lines.

The readings appear under **Awareness** in the phone UI, and any BLE device that
follows you across places shows up under **Safety → Possible followers**.
