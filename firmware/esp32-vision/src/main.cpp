#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>
#include <esp_timer.h>
#include <img_converters.h>

#define CAMERA_MODEL_ESP32S3_EYE
#include "camera_pins.h"

const char* ssid = "ESP32-CAM-AP";
const char* password = "robot2026";

WebServer server(80);

void startCameraServer();

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println();
  Serial.println("Starting ESP32-S3 camera firmware...");
  Serial.println("Camera model: ESP32S3_EYE");
  Serial.println("Using COM4 serial monitor workflow. Expect AP: ");
  Serial.println(ssid);

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
  config.xclk_freq_hz = 16000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_SVGA;
  config.jpeg_quality = 12;
  config.fb_count = 2;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.grab_mode = CAMERA_GRAB_LATEST;

  if (psramFound()) {
    config.fb_count = 2;
    config.fb_location = CAMERA_FB_IN_PSRAM;
    Serial.println("PSRAM found: using 2 frame buffers");
  } else {
    config.fb_count = 1;
    config.fb_location = CAMERA_FB_IN_DRAM;
    config.frame_size = FRAMESIZE_VGA;
    Serial.println("PSRAM not found: using 1 frame buffer and VGA resolution");
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x\n", err);
    Serial.println("Check camera pin mapping, model selection, and power supply.");
    return;
  }

  Serial.println("Camera initialized successfully.");
  WiFi.mode(WIFI_AP);
  WiFi.softAP(ssid, password);
  IPAddress ip = WiFi.softAPIP();
  Serial.printf("ESP32-CAM AP started: http://%s\n", ip.toString().c_str());

  startCameraServer();
}

void loop() {
  server.handleClient();
}

String getContentType(String filename) {
  if (server.hasArg("download")) return "application/octet-stream";
  else if (filename.endsWith(".jpg")) return "image/jpeg";
  if (filename.endsWith(".html")) return "text/html";
  if (filename.endsWith(".css")) return "text/css";
  if (filename.endsWith(".js")) return "application/javascript";
  return "text/plain";
}

bool handleJPGStream(void) {
  WiFiClient client = server.client();
  String response = "HTTP/1.1 200 OK\r\n";
  response += "Content-Type: multipart/x-mixed-replace; boundary=frame\r\n\r\n";
  server.sendContent(response);

  while (true) {
    camera_fb_t* fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("Camera capture failed");
      return false;
    }

    response = "--frame\r\n";
    response += "Content-Type: image/jpeg\r\n";
    response += "Content-Length: " + String(fb->len) + "\r\n\r\n";
    server.sendContent(response);
    server.client().write(fb->buf, fb->len);
    server.sendContent("\r\n");
    esp_camera_fb_return(fb);

    if (!client.connected()) {
      break;
    }
  }

  return true;
}

void handleRoot() {
  String html = "<html><head><title>ESP32-CAM Stream</title></head><body>";
  html += "<h1>ESP32-CAM MJPEG Stream</h1>";
  html += "<img src=\"/stream\" width=640 />";
  html += "</body></html>";
  server.send(200, "text/html", html);
}

void startCameraServer() {
  server.on("/", HTTP_GET, handleRoot);
  server.on("/stream", HTTP_GET, []() {
    handleJPGStream();
  });
  server.begin();
}
