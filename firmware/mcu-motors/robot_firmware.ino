#include <SoftwareSerial.h>
#include <Wire.h>

// SoftwareSerial pins for Rock64 communication
static const uint8_t kSoftRxPin = 2;  // Arduino receives from Rock64
static const uint8_t kSoftTxPin = 4;  // Arduino transmits to Rock64
static const long kSerialBaud = 9600;

// MPU6050 I2C address and registers
static const uint8_t kMPU6050Address = 0x68;
static const uint8_t kMPU6050PowerMgmt1 = 0x6B;
static const uint8_t kMPU6050AccelXOutH = 0x3B;
static const uint8_t kMPU6050GyroXOutH = 0x43;

// Motor shield pin assignments
static const uint8_t kLeftSpeedPin = 5;
static const uint8_t kLeftDirPinA = 7;
static const uint8_t kLeftDirPinB = 8;
static const uint8_t kRightSpeedPin = 6;
static const uint8_t kRightDirPinA = 9;
static const uint8_t kRightDirPinB = 11;

// Telemetry interval
static const unsigned long kTelemetryIntervalMs = 50;

SoftwareSerial rock64Serial(kSoftRxPin, kSoftTxPin);

char incomingBuffer[64];
uint8_t bufferIndex = 0;
bool packetInProgress = false;
unsigned long lastTelemetryMillis = 0;

void setup() {
  pinMode(kLeftSpeedPin, OUTPUT);
  pinMode(kLeftDirPinA, OUTPUT);
  pinMode(kLeftDirPinB, OUTPUT);
  pinMode(kRightSpeedPin, OUTPUT);
  pinMode(kRightDirPinA, OUTPUT);
  pinMode(kRightDirPinB, OUTPUT);

  digitalWrite(kLeftDirPinA, LOW);
  digitalWrite(kLeftDirPinB, LOW);
  digitalWrite(kRightDirPinA, LOW);
  digitalWrite(kRightDirPinB, LOW);

  Wire.begin();
  initializeMPU6050();

  rock64Serial.begin(kSerialBaud);
  sendDebug("READY\n");
}

void loop() {
  readSerialPackets();
  unsigned long now = millis();
  if (now - lastTelemetryMillis >= kTelemetryIntervalMs) {
    lastTelemetryMillis = now;
    sendTelemetry();
  }
}

void initializeMPU6050() {
  Wire.beginTransmission(kMPU6050Address);
  Wire.write(kMPU6050PowerMgmt1);
  Wire.write(0x00);  // wake up MPU6050
  Wire.endTransmission();
  delay(100);
}

void sendDebug(const char* message) {
  rock64Serial.print(message);
}

void readSerialPackets() {
  while (rock64Serial.available() > 0) {
    char c = rock64Serial.read();
    if (c == '<') {
      packetInProgress = true;
      bufferIndex = 0;
      memset(incomingBuffer, 0, sizeof(incomingBuffer));
      continue;
    }

    if (packetInProgress) {
      if (c == '>') {
        packetInProgress = false;
        incomingBuffer[bufferIndex < sizeof(incomingBuffer) ? bufferIndex : sizeof(incomingBuffer) - 1] = '\0';
        processPacket(incomingBuffer);
      } else if (bufferIndex < sizeof(incomingBuffer) - 1) {
        incomingBuffer[bufferIndex++] = c;
      }
    }
  }
}

void processPacket(const char* packet) {
  if (packet == nullptr || packet[0] == '\0') {
    return;
  }

  const char* token = strtok((char*)packet, ",");
  if (token == nullptr) {
    return;
  }

  if (strcmp(token, "MOVE") == 0) {
    const char* leftValue = strtok(nullptr, ",");
    const char* rightValue = strtok(nullptr, ",");
    if (leftValue != nullptr && rightValue != nullptr) {
      int leftSpeed = atoi(leftValue);
      int rightSpeed = atoi(rightValue);
      applyDriveCommand(leftSpeed, rightSpeed);
    }
  }
}

void applyDriveCommand(int leftSpeed, int rightSpeed) {
  setMotor(kLeftDirPinA, kLeftDirPinB, kLeftSpeedPin, leftSpeed);
  setMotor(kRightDirPinA, kRightDirPinB, kRightSpeedPin, rightSpeed);
}

void setMotor(uint8_t dirPinA, uint8_t dirPinB, uint8_t speedPin, int speedValue) {
  bool forward = speedValue > 0;
  bool backward = speedValue < 0;
  uint8_t pwm = min(abs(speedValue), 255);

  if (forward) {
    digitalWrite(dirPinA, HIGH);
    digitalWrite(dirPinB, LOW);
  } else if (backward) {
    digitalWrite(dirPinA, LOW);
    digitalWrite(dirPinB, HIGH);
  } else {
    digitalWrite(dirPinA, LOW);
    digitalWrite(dirPinB, LOW);
  }

  analogWrite(speedPin, pwm);
}

void sendTelemetry() {
  int16_t accelX, accelY, accelZ, gyroX, gyroY, gyroZ;
  readMPU6050(accelX, accelY, accelZ, gyroX, gyroY, gyroZ);

  rock64Serial.print("TELEMETRY,");
  rock64Serial.print(gyroX);
  rock64Serial.print(",");
  rock64Serial.print(gyroY);
  rock64Serial.print(",");
  rock64Serial.print(gyroZ);
  rock64Serial.print(",");
  rock64Serial.print(accelX);
  rock64Serial.print(",");
  rock64Serial.print(accelY);
  rock64Serial.print(",");
  rock64Serial.print(accelZ);
  rock64Serial.print("\n");
}

void readMPU6050(int16_t &accelX, int16_t &accelY, int16_t &accelZ, int16_t &gyroX, int16_t &gyroY, int16_t &gyroZ) {
  Wire.beginTransmission(kMPU6050Address);
  Wire.write(kMPU6050AccelXOutH);
  Wire.endTransmission(false);

  Wire.requestFrom(kMPU6050Address, (uint8_t)14);
  if (Wire.available() >= 14) {
    accelX = (Wire.read() << 8) | Wire.read();
    accelY = (Wire.read() << 8) | Wire.read();
    accelZ = (Wire.read() << 8) | Wire.read();
    Wire.read();
    Wire.read();
    Wire.read();
    gyroX = (Wire.read() << 8) | Wire.read();
    gyroY = (Wire.read() << 8) | Wire.read();
    gyroZ = (Wire.read() << 8) | Wire.read();
  } else {
    accelX = accelY = accelZ = gyroX = gyroY = gyroZ = 0;
  }
}
