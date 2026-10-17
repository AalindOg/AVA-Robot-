/*
 * AVA v1.0 — Phase 1 Firmware
 * Board: XIAO ESP32-S3 Sense
 * Layer: AVA Sense + AVA Bridge (Layers 1-2)
 * Features:
 *   - PDM microphone streaming over WebSocket
 *   - IMU tap detection (wake gesture)
 *   - WiFi + WebSocket to server
 *   - Power-optimized idle loop
 */

#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <Adafruit_LSM6DS3TRC.h>
#include <driver/i2s.h>

// ─── Config (change in secrets.h or hardcode) ───────────────────────────────
#ifndef WIFI_SSID
  #define WIFI_SSID     "YOUR_WIFI_SSID"
  #define WIFI_PASS     "YOUR_WIFI_PASS"
#endif
#define SERVER_HOST     "192.168.1.100"   // your Ubuntu server IP
#define SERVER_PORT     5013               // AVA server WebSocket port
#define WS_PATH         "/ws/audio"

#define SAMPLE_RATE     16000
#define AUDIO_BUF_MS    100                // 100ms chunks = 3200 bytes @ 16kHz mono 16-bit
#define TAP_THRESHOLD   2.5                // G-force threshold for tap
#define TAP_COOLDOWN_MS 800                // debounce

// ─── Globals ────────────────────────────────────────────────────────────────
WebSocketsClient ws;
Adafruit_LSM6DS3TRC imu;

const size_t audioChunkBytes = (SAMPLE_RATE * 2 * AUDIO_BUF_MS) / 1000; // 16-bit mono
uint8_t *audioBuffer = nullptr;

bool wsConnected = false;
uint32_t lastTapMs = 0;
uint32_t framesSent = 0;

// ─── I2S / PDM Microphone ───────────────────────────────────────────────────
void initPDM() {
  i2s_config_t i2s_cfg = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX | I2S_MODE_PDM),
    .sample_rate = SAMPLE_RATE,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 4,
    .dma_buf_len = 512,
    .use_apll = false,
    .tx_desc_auto_clear = false,
    .fixed_mclk = 0
  };
  i2s_pin_config_t pin_cfg = {
    .mck_io_num = I2S_PIN_NO_CHANGE,
    .bck_io_num = I2S_PIN_NO_CHANGE,
    .ws_io_num = 42,          // D1 / CLK on XIAO ESP32S3 Sense
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num = 41         // D0 / DATA on XIAO ESP32S3 Sense
  };
  i2s_driver_install(I2S_NUM_0, &i2s_cfg, 0, NULL);
  i2s_set_pin(I2S_NUM_0, &pin_cfg);
  i2s_start(I2S_NUM_0);
}

// ─── WebSocket ──────────────────────────────────────────────────────────────
void wsEvent(WStype_t type, uint8_t *payload, size_t len) {
  switch (type) {
    case WStype_DISCONNECTED:
      Serial.println("[WS] Disconnected");
      wsConnected = false;
      break;
    case WStype_CONNECTED:
      Serial.println("[WS] Connected to server");
      wsConnected = true;
      {
        DynamicJsonDocument hello(256);
        hello["type"] = "device_hello";
        hello["device"] = "AVA_v1";
        hello["sample_rate"] = SAMPLE_RATE;
        hello["format"] = "pcm_s16le";
        String msg;
        serializeJson(hello, msg);
        ws.sendTXT(msg);
      }
      break;
    case WStype_TEXT: {
      Serial.printf("[WS] RX: %s\n", payload);
      DynamicJsonDocument cmd(512);
      deserializeJson(cmd, payload);
      const char *typeStr = cmd["type"];
      if (strcmp(typeStr, "start_listening") == 0) {
        Serial.println("[CMD] Server requested listening mode");
        // TODO: set listening state flag
      } else if (strcmp(typeStr, "stop_listening") == 0) {
        Serial.println("[CMD] Server requested stop");
      }
      break;
    }
    default:
      break;
  }
}

// ─── IMU ────────────────────────────────────────────────────────────────────
void initIMU() {
  if (!imu.begin_I2C()) {
    Serial.println("[IMU] LSM6DS3TR-C not found — check wiring");
  } else {
    Serial.println("[IMU] Ready");
    imu.configInt1(false, false, true); // INT1 = DRDY_GYRO (unused here)
  }
}

bool checkTap() {
  sensors_event_t accel, gyro, temp;
  imu.getEvent(&accel, &gyro, &temp);
  float mag = sqrt(accel.acceleration.x * accel.acceleration.x +
                   accel.acceleration.y * accel.acceleration.y +
                   accel.acceleration.z * accel.acceleration.z);
  float g = mag / 9.81f;
  if (g > TAP_THRESHOLD && (millis() - lastTapMs) > TAP_COOLDOWN_MS) {
    lastTapMs = millis();
    return true;
  }
  return false;
}

// ─── WiFi ───────────────────────────────────────────────────────────────────
void connectWiFi() {
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("[WiFi] Connecting");
  int attempt = 0;
  while (WiFi.status() != WL_CONNECTED && attempt < 30) {
    delay(500);
    Serial.print(".");
    attempt++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[WiFi] Connected, IP: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\n[WiFi] FAILED — check credentials");
  }
}

// ─── Setup ──────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n╔══════════════════════════════╗");
  Serial.println("║     AVA v1.0  —  BOOT       ║");
  Serial.println("╚══════════════════════════════╝");

  // Allocate audio buffer in PSRAM if available
  if (psramFound()) {
    audioBuffer = (uint8_t *)ps_malloc(audioChunkBytes);
    Serial.printf("[PSRAM] Found %d MB\n", ESP.getPsramSize() / 1024 / 1024);
  } else {
    audioBuffer = (uint8_t *)malloc(audioChunkBytes);
  }
  if (!audioBuffer) {
    Serial.println("[FATAL] Audio buffer alloc failed");
    while (1) delay(100);
  }

  connectWiFi();
  initPDM();
  initIMU();

  ws.begin(SERVER_HOST, SERVER_PORT, WS_PATH);
  ws.onEvent(wsEvent);
  ws.setReconnectInterval(3000);
  ws.enableHeartbeat(5000, 3000, 2);

  Serial.println("[LOOP] Starting main loop");
}

// ─── Main Loop ──────────────────────────────────────────────────────────────
void loop() {
  ws.loop();

  // 1. Check tap gesture
  if (checkTap()) {
    Serial.println("[GESTURE] Tap detected — triggering capture");
    DynamicJsonDocument evt(128);
    evt["type"] = "gesture";
    evt["gesture"] = "tap";
    String msg;
    serializeJson(evt, msg);
    if (wsConnected) ws.sendTXT(msg);
  }

  // 2. Stream audio when connected
  if (wsConnected) {
    size_t bytesRead = 0;
    esp_err_t err = i2s_read(I2S_NUM_0, audioBuffer, audioChunkBytes, &bytesRead, pdMS_TO_TICKS(AUDIO_BUF_MS + 20));
    if (err == ESP_OK && bytesRead > 0) {
      ws.sendBIN(audioBuffer, bytesRead);
      framesSent++;
      if (framesSent % 100 == 0) {
        Serial.printf("[AUDIO] Sent %lu chunks\n", framesSent);
      }
    }
  } else {
    // Not connected: drain I2S buffer so it doesn't overflow
    size_t bytesRead = 0;
    i2s_read(I2S_NUM_0, audioBuffer, audioChunkBytes, &bytesRead, pdMS_TO_TICKS(50));
    delay(50); // save power when disconnected
  }

  // 3. Periodic status every 5s
  static uint32_t lastStatus = 0;
  if (millis() - lastStatus > 5000) {
    lastStatus = millis();
    if (wsConnected) {
      DynamicJsonDocument status(128);
      status["type"] = "status";
      status["heap"] = ESP.getFreeHeap();
      status["psram"] = ESP.getFreePsram();
      status["rssi"] = WiFi.RSSI();
      String msg;
      serializeJson(status, msg);
      ws.sendTXT(msg);
    }
  }
}