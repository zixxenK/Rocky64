#include "esp_camera.h"
#include <WiFi.h>
#include <ESPAsyncWebServer.h>
#include <esp_timer.h>
#include <img_converters.h>

#define CAMERA_MODEL_ESP32S3_EYE
#include "camera_pins.h"

// ---- Network credentials ----
const char* ap_ssid = "ESP32-CAM-AP";
const char* ap_password = "robot2026";

const bool use_station_mode = true;
const char* sta_ssid = "TELUS4424";
const char* sta_password = "camncarm2021";

// ---- Async web server (non-blocking, multi-client) ----
AsyncWebServer server(80);

bool wifiConnected = false;
bool accessPointActive = false;
unsigned long lastWiFiReconnect = 0;
const unsigned long wifiReconnectInterval = 10000;

// Forward declarations
bool startWiFiStation();
IPAddress startAccessPoint();
void onWiFiEvent(WiFiEvent_t event);
void startCameraServer();

void setup() {
  Serial.begin(115200);
  Serial.println();
  Serial.println("Starting ESP32-S3 camera firmware...");
  Serial.println("Camera model: ESP32S3_EYE");

  camera_config_t config;
  memset(&config, 0, sizeof(config));
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_QVGA;
  config.jpeg_quality = 20;
  config.fb_count = 2;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.grab_mode = CAMERA_GRAB_LATEST;

  if (psramFound()) {
    config.fb_count = 2;
    config.fb_location = CAMERA_FB_IN_PSRAM;
  } else {
    config.fb_count = 1;
    config.fb_location = CAMERA_FB_IN_DRAM;
    config.frame_size = FRAMESIZE_QVGA;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x\n", err);
    return;
  }

  if (use_station_mode && strlen(sta_ssid) > 0 && strlen(sta_password) > 0) {
    if (!startWiFiStation()) {
      startAccessPoint();
    }
  } else {
    startAccessPoint();
  }

  startCameraServer();
}

bool startWiFiStation() {
  WiFi.disconnect(true);
  WiFi.mode(WIFI_STA);
  accessPointActive = false;
  WiFi.setHostname("esp32-cam");
  WiFi.setTxPower(WIFI_POWER_19_5dBm);
  WiFi.setAutoReconnect(true);
  WiFi.setSleep(false);
  WiFi.onEvent(onWiFiEvent);
  WiFi.begin(sta_ssid, sta_password);

  const int max_attempts = 30;
  int attempt = 0;
  while (WiFi.status() != WL_CONNECTED && attempt < max_attempts) {
    delay(1000);
    attempt++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    wifiConnected = true;
    accessPointActive = false;
    return true;
  }
  return false;
}

void onWiFiEvent(WiFiEvent_t event) {
  if (event == ARDUINO_EVENT_WIFI_STA_GOT_IP) {
    wifiConnected = true;
    accessPointActive = false;
  } else if (event == ARDUINO_EVENT_WIFI_STA_DISCONNECTED) {
    wifiConnected = false;
    WiFi.reconnect();
  }
}

IPAddress startAccessPoint() {
  WiFi.mode(WIFI_AP);
  WiFi.softAP(ap_ssid, ap_password);
  accessPointActive = true;
  wifiConnected = false;
  return WiFi.softAPIP();
}

void loop() {
  // WiFi reconnect watchdog (lightweight, non-blocking)
  if (use_station_mode && !wifiConnected && millis() - lastWiFiReconnect >= wifiReconnectInterval) {
    lastWiFiReconnect = millis();
    if (WiFi.status() != WL_CONNECTED) {
      WiFi.reconnect();
    }
  }
  delay(100);  // main loop only handles WiFi reconnect
}

// ---- Async web server routes ----

// MJPEG stream handler — each client gets its own async response that
// sends frames independently.  Multiple clients can connect at once
// without blocking the server.
class MjpegStreamResponse : public AsyncAbstractResponse {
  public:
    MjpegStreamResponse() {
      _code = 200;
      _contentType = "multipart/x-mixed-replace; boundary=frame";
      _sendContentLength = false;
      _state = 0;
    }

    bool _sourceValid() const override { return true; }

    size_t _fillBuffer(uint8_t* buf, size_t maxLen) override {
      // State machine: alternate between sending boundary+headers and frame data
      if (_state == 0) {
        // Capture a frame
        _fb = esp_camera_fb_get();
        if (!_fb) return 0;

        // Build boundary + headers
        int headerLen = snprintf(
            (char*)_headerBuf, sizeof(_headerBuf),
            "--frame\r\n"
            "Content-Type: image/jpeg\r\n"
            "Content-Length: %u\r\n\r\n",
            _fb->len);

        if ((size_t)headerLen > maxLen) {
          esp_camera_fb_return(_fb);
          _fb = nullptr;
          return 0;
        }

        memcpy(buf, _headerBuf, headerLen);
        _frameOffset = 0;
        _state = 1;
        return headerLen;
      }

      if (_state == 1 && _fb) {
        size_t remaining = _fb->len - _frameOffset;
        size_t toSend = (remaining < maxLen) ? remaining : maxLen;
        memcpy(buf, _fb->buf + _frameOffset, toSend);
        _frameOffset += toSend;

        if (_frameOffset >= _fb->len) {
          esp_camera_fb_return(_fb);
          _fb = nullptr;
          _state = 2;
        }
        return toSend;
      }

      if (_state == 2) {
        // End-of-frame newline
        if (maxLen >= 2) {
          buf[0] = '\r';
          buf[1] = '\n';
          _state = 0;  // ready for next frame
          return 2;
        }
        return 0;
      }

      return 0;
    }

  private:
    camera_fb_t* _fb = nullptr;
    size_t _frameOffset = 0;
    int _state = 0;  // 0=header, 1=frame data, 2=trailing CRLF
    char _headerBuf[128];
};

void startCameraServer() {
  // Root page
  server.on("/", HTTP_GET, [](AsyncWebServerRequest* request) {
    String html = "<html><head><title>ESP32-CAM Stream</title></head>"
                  "<body><h1>ESP32-CAM MJPEG Stream</h1>"
                  "<img src=\"/stream\" width=640 /></body></html>";
    request->send(200, "text/html", html);
  });

  // MJPEG stream — async, non-blocking, supports multiple clients
  server.on("/stream", HTTP_GET, [](AsyncWebServerRequest* request) {
    request->send(new MjpegStreamResponse());
  });

  // Single JPEG capture
  server.on("/capture", HTTP_GET, [](AsyncWebServerRequest* request) {
    camera_fb_t* fb = esp_camera_fb_get();
    if (!fb) {
      request->send(500, "text/plain", "Capture failed");
      return;
    }
    AsyncWebServerResponse* response = request->beginResponse_P(
        200, "image/jpeg", fb->buf, fb->len);
    response->addHeader("Content-Disposition", "inline; filename=capture.jpg");
    request->send(response);
    esp_camera_fb_return(fb);
  });

  // Status JSON
  server.on("/status", HTTP_GET, [](AsyncWebServerRequest* request) {
    String mode = wifiConnected ? "station_connected" : "access_point";
    String activeSsid = wifiConnected ? sta_ssid : ap_ssid;
    IPAddress ip = wifiConnected ? WiFi.localIP() : WiFi.softAPIP();

    String json = "{";
    json += "\"wifi_mode\":\"" + mode + "\",";
    json += "\"ssid\":\"" + activeSsid + "\",";
    json += "\"ip\":\"" + ip.toString() + "\"";
    json += "}";

    request->send(200, "application/json", json);
  });

  server.begin();
  Serial.println("Async HTTP Web Server started successfully.");
}
