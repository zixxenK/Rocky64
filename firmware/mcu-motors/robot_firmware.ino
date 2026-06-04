#include <Wire.h>

static const long kSerialBaud = 115200;

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

  Serial.begin(kSerialBaud);
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
  Serial.print(message);
}

void readSerialPackets() {
  while (Serial.available() > 0) {
    char c = Serial.read();
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
  if (packet == nullptr) return;

  // We make a working copy because strtok modifies the input string
  char buffer[64];
  strncpy(buffer, packet, sizeof(buffer) - 1);
  buffer[sizeof(buffer) - 1] = '\0';

  char* token1 = strtok(buffer, ",");
  char* token2 = strtok(nullptr, ",");
  char* token3 = strtok(nullptr, ",");

  // Ensure all parts exist before processing
  if (token1 != nullptr && token2 != nullptr && token3 != nullptr) {
    int id = atoi(token1);
    char type = token2[0];
    int value = atoi(token3);

    // Logic: Map the command 'type' to motor behavior
    int leftSpeed = 0;
    int rightSpeed = 0;

    switch (type) {
      case 'F': // Forward
        leftSpeed = value;
        rightSpeed = value;
        break;
      case 'B': // Backward
        leftSpeed = -value;
        rightSpeed = -value;
        break;
      case 'L': // Spin Left
        leftSpeed = -value;
        rightSpeed = value;
        break;
      case 'R': // Spin Right
        leftSpeed = value;
        rightSpeed = -value;
        break;
      default:
        leftSpeed = 0;
        rightSpeed = 0;
        break;
    }

    applyDriveCommand(leftSpeed, rightSpeed);
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

  Serial.print("TELEMETRY,");
  Serial.print(gyroX);
  Serial.print(",");
  Serial.print(gyroY);
  Serial.print(",");
  Serial.print(gyroZ);
  Serial.print(",");
  Serial.print(accelX);
  Serial.print(",");
  Serial.print(accelY);
  Serial.print(",");
  Serial.print(accelZ);
  Serial.print("\n");
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
