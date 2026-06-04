#include "esp_camera.h"
#include <WiFi.h>
#include <WiFiUdp.h> // <-- INJECTED: Missing library for network packets
#include <WebServer.h>
#include <esp_timer.h>
#include <img_converters.h>

#define CAMERA_MODEL_ESP32S3_EYE
#include "camera_pins.h"

const char* ap_ssid = "ESP32-CAM-AP";
const char* ap_password = "robot2026";

const bool use_station_mode = true;
const char* sta_ssid = "TELUS4424";
const char* sta_password = "camncarm2021";

// --- INJECTED: UDP Network Variables ---
WiFiUDP udp;
const unsigned int localUdpPort = 8888; // Listens to the port your ROS2 node targets
char udpPacketBuffer[255]; 

WebServer server(80);
bool wifiConnected = false;
bool accessPointActive = false;
unsigned long lastWiFiReconnect = 0;
const unsigned long wifiReconnectInterval = 10000;

// Function Prototypes
void startCameraServer();
bool startWiFiStation();
IPAddress startAccessPoint();
void onWiFiEvent(WiFiEvent_t event);
void handleStatus();
void handleRoot();
void handleSingleJPG();
bool handleJPGStream();

void setup() {
  Serial.begin(115200); // This talks down the wire to the Uno
  Serial.println();
  Serial.println("Starting ESP32-S3 camera + UDP Bridge firmware...");
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
    if (startWiFiStation()) {
      // Connect UDP once Wi-Fi is green-lit
      udp.begin(localUdpPort);
    } else {
      startAccessPoint();
      udp.begin(localUdpPort);
    }
  } else {
    startAccessPoint();
    udp.begin(localUdpPort);
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
    udp.begin(localUdpPort); // Double check UDP restarts on fresh IP
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
  server.handleClient();
  
  // --- INJECTED: Read ROS2 packets from Wi-Fi and forward directly to Uno ---
  int packetSize = udp.parsePacket();
  if (packetSize) {
    int len = udp.read(udpPacketBuffer, 255);
    if (len > 0) {
      udpPacketBuffer[len] = '\0';
      // This sends '<1,B,85>\n' physically down the TX pin straight to the Uno's RX pin!
      Serial.print(udpPacketBuffer); 
    }
  }

  yield();

  if (use_station_mode && !wifiConnected && millis() - lastWiFiReconnect >= wifiReconnectInterval) {
    lastWiFiReconnect = millis();
    if (WiFi.status() != WL_CONNECTED) {
      WiFi.reconnect();
    }
  }
}

// Set up server routes and start the server
void startCameraServer() {
  server.on("/", handleRoot);
  server.on("/stream", []() {
    handleJPGStream();
  });
  server.on("/capture", handleSingleJPG);
  server.on("/status", handleStatus);
  server.begin();
  Serial.println("HTTP Web Server started successfully.");
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
  if (!client || !client.connected()) return false;
  client.print("HTTP/1.1 200 OK\r\n");
  client.print("Content-Type: multipart/x-mixed-replace; boundary=frame\r\n\r\n");
  while (client.connected()) {
    camera_fb_t* fb = esp_camera_fb_get();
    if (!fb) return false;
    client.print("--frame\r\n");
    client.print("Content-Type: image/jpeg\r\n");
    client.print("Content-Length: ");
    client.print(fb->len);
    client.print("\r\n\r\n");
    client.write(fb->buf, fb->len);
    client.print("\r\n");
    esp_camera_fb_return(fb);
    if (!client.connected()) break;
    delay(1);
    yield();
  }
  return true;
}

void handleRoot() {
  String html = "<html><head><title>ESP32-CAM Stream</title></head><body><h1>ESP32-CAM MJPEG Stream</h1><img src=\"/stream\" width=640 /></body></html>";
  server.send(200, "text/html", html);
}

void handleSingleJPG() {
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) { server.send(500, "text/plain", "Capture failed"); return; }
  server.sendHeader("Content-Disposition", "inline; filename=capture.jpg");
  server.send_P(200, "image/jpeg", (const char*)fb->buf, fb->len);
  esp_camera_fb_return(fb);
}

void handleStatus() {
  String mode = wifiConnected ? "station_connected" : "access_point"; 
  String activeSsid = wifiConnected ? sta_ssid : ap_ssid; 
  IPAddress ip = wifiConnected ? WiFi.localIP() : WiFi.softAPIP();
  
  String json = "{";
  json += "\"wifi_mode\":\"" + mode + "\",";
  json += "\"ssid\":\"" + activeSsid + "\",";
  json += "\"ip\":\"" + ip.toString() + "\"";
  json += "}";
  
  server.send(200, "application/json", json);
}