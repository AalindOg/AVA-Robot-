/*
 * AVA v1.0 stable — Audio Bridge Firmware
 * Board: XIAO ESP32-S3 Sense
 * PDM mic streaming + IMU tap + WebSocket
 */
#include <Arduino.h>
#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <Adafruit_LSM6DS3TRC.h>
#include <driver/i2s.h>

#define WIFI_SSID     "YOUR_WIFI_SSID"
#define WIFI_PASS     "YOUR_WIFI_PASSWORD"
#define SERVER_HOST   "192.168.70.49"
#define SERVER_PORT   5013
#define WS_PATH       "/ws/audio"
#define SAMPLE_RATE   16000
#define AUDIO_BUF_MS  80
#define TAP_THRESHOLD 2.5f
#define TAP_COOLDOWN  2000

WebSocketsClient ws;
Adafruit_LSM6DS3TRC imu;
bool imuReady = false;
const size_t CHUNK = (SAMPLE_RATE * 2 * AUDIO_BUF_MS) / 1000;
uint8_t *buf = nullptr;
bool wsOk = false;
uint32_t lastTap = 0, framesSent = 0;

void initPDM() {
  i2s_config_t cfg = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX | I2S_MODE_PDM),
    .sample_rate = SAMPLE_RATE, .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 4, .dma_buf_len = 512,
    .use_apll = false, .tx_desc_auto_clear = false, .fixed_mclk = 0
  };
  i2s_pin_config_t pins = {
    .mck_io_num = I2S_PIN_NO_CHANGE, .bck_io_num = I2S_PIN_NO_CHANGE,
    .ws_io_num = 42, .data_out_num = I2S_PIN_NO_CHANGE, .data_in_num = 41
  };
  i2s_driver_install(I2S_NUM_0, &cfg, 0, NULL);
  i2s_set_pin(I2S_NUM_0, &pins); i2s_start(I2S_NUM_0);
}

void wsEvent(WStype_t type, uint8_t *p, size_t l) {
  if (type == WStype_CONNECTED) {
    wsOk = true; Serial.println("[WS] OK");
    JsonDocument d; d["type"]="device_hello"; d["device"]="AVA_v1";
    d["sample_rate"]=SAMPLE_RATE; d["format"]="pcm_s16le";
    String s; serializeJson(d, s); ws.sendTXT(s);
  } else if (type == WStype_DISCONNECTED) { wsOk = false; Serial.println("[WS] DC"); }
}

void initIMU() {
  Wire.begin(44, 43);
  imuReady = imu.begin_I2C(0x6A);
  Serial.println(imuReady ? "[IMU] Ready" : "[IMU] Off");
}

bool checkTap() {
  if (!imuReady) return false;
  sensors_event_t a,g,t; imu.getEvent(&a,&g,&t);
  float mag = sqrtf(a.acceleration.x*a.acceleration.x + a.acceleration.y*a.acceleration.y + a.acceleration.z*a.acceleration.z) / 9.81f;
  if (mag > TAP_THRESHOLD && millis() - lastTap > TAP_COOLDOWN) { lastTap = millis(); return true; }
  return false;
}

void connectWiFi() {
  WiFi.setAutoReconnect(true);
  WiFi.setHostname("ava-necklace");
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("[WiFi]"); int i=0;
  while (WiFi.status()!=WL_CONNECTED && i++<60) { delay(500); Serial.print("."); }
  Serial.println(WiFi.status()==WL_CONNECTED ? " OK "+WiFi.localIP().toString() : " FAIL");
}

void setup() {
  Serial.begin(115200); delay(800);
  Serial.println("\n=== AVA v1.0 ===");
  buf = psramFound() ? (uint8_t*)ps_malloc(CHUNK) : (uint8_t*)malloc(CHUNK);
  if (!buf) { Serial.println("[FATAL] OOM"); while(1)delay(100); }
  connectWiFi(); initPDM(); initIMU();
  ws.begin(SERVER_HOST, SERVER_PORT, WS_PATH);
  ws.onEvent(wsEvent); ws.setReconnectInterval(3000);
  ws.enableHeartbeat(15000, 5000, 3);
  Serial.println("[READY]");
}

void loop() {
  ws.loop();
  if (checkTap()) {
    JsonDocument d; d["type"]="gesture"; d["gesture"]="tap";
    String s; serializeJson(d, s); if (wsOk) ws.sendTXT(s);
  }
  if (wsOk) {
    size_t r=0;
    if (i2s_read(I2S_NUM_0, buf, CHUNK, &r, pdMS_TO_TICKS(AUDIO_BUF_MS+20))==ESP_OK && r>0) {
      ws.sendBIN(buf, r);
      if (++framesSent%300==0) Serial.printf("[AUDIO] %lu\n", framesSent);
    }
  } else { size_t r; i2s_read(I2S_NUM_0,buf,CHUNK,&r,pdMS_TO_TICKS(50)); delay(50); }
  static uint32_t lastHb=0;
  if (millis()-lastHb>15000 && wsOk) {
    lastHb=millis();
    JsonDocument d; d["type"]="status"; d["heap"]=ESP.getFreeHeap(); d["rssi"]=WiFi.RSSI();
    String s; serializeJson(d,s); ws.sendTXT(s);
  }
}