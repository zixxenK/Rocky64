#include <Arduino.h>
#include <AFMotor.h>
#include <avr/wdt.h>
#include <string.h>
#include <stdlib.h>

const unsigned long HEARTBEAT_TIMEOUT_MS = 200;
const size_t SERIAL_BUF_SIZE = 32;

AF_DCMotor leftMotor(3);  // Left motor on channel 3
AF_DCMotor rightMotor(1); // Right motor on channel 1

char serialBuffer[SERIAL_BUF_SIZE];
size_t bufferIndex = 0;
bool bufferInProgress = false;
unsigned long lastCommandTime = 0;

void readSerialInput();
void parseCommand(char* packet);
void checkHeartbeat();

void setup() {
  Serial.begin(115200);
  wdt_enable(WDTO_500MS);

  leftMotor.setSpeed(0);
  rightMotor.setSpeed(0);
  leftMotor.run(RELEASE);
  rightMotor.run(RELEASE);

  lastCommandTime = millis();
  Serial.println("UNO READY");
}

void loop() {
  wdt_reset();
  checkHeartbeat();
  readSerialInput();
}

void readSerialInput() {
  while (Serial.available() > 0) {
    char incomingChar = Serial.read();
    if (incomingChar == '<') {
      bufferInProgress = true;
      bufferIndex = 0;
      memset(serialBuffer, 0, SERIAL_BUF_SIZE);
    } else if (incomingChar == '>') {
      bufferInProgress = false;
      serialBuffer[bufferIndex < SERIAL_BUF_SIZE ? bufferIndex : SERIAL_BUF_SIZE - 1] = '\0';
      Serial.print("RECEIVED: ");
      Serial.println(serialBuffer);
      parseCommand(serialBuffer);
      lastCommandTime = millis();
    } else if (bufferInProgress && bufferIndex < SERIAL_BUF_SIZE - 1) {
      serialBuffer[bufferIndex++] = incomingChar;
    }
  }
}

void parseCommand(char* packet) {
  if (packet == NULL || packet[0] == '\0') {
    return;
  }

  char* token = strtok(packet, ",");
  if (token == NULL) return;

  int motorId = atoi(token);
  token = strtok(NULL, ",");
  if (token == NULL) return;

  char dir = token[0];
  token = strtok(NULL, ",");
  if (token == NULL) return;

  int speedVal = atoi(token);
  speedVal = constrain(speedVal, 0, 255);

  uint8_t runMode = RELEASE;
  if (dir == 'F') runMode = FORWARD;
  else if (dir == 'B') runMode = BACKWARD;
  else if (dir == 'S') runMode = RELEASE;

  if (motorId == 1) {
    rightMotor.setSpeed(speedVal);
    rightMotor.run(runMode);
  } else if (motorId == 2) {
    leftMotor.setSpeed(speedVal);
    leftMotor.run(runMode);
  } else if (motorId == 0) {
    leftMotor.setSpeed(speedVal);
    rightMotor.setSpeed(speedVal);
    leftMotor.run(runMode);
    rightMotor.run(runMode);
  }
}

void checkHeartbeat() {
  if (millis() - lastCommandTime > HEARTBEAT_TIMEOUT_MS) {
    leftMotor.run(RELEASE);
    rightMotor.run(RELEASE);
  }
}
