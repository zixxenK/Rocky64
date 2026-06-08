#include <Arduino.h>
#include <Servo.h>
#include <avr/wdt.h>
#include <string.h>
#include <stdlib.h>

// --- FORWARD DECLARATIONS (Fixes "not declared in this scope" errors) ---
void stopMotors();
void setMotor(int motorId, char dir, int speed);
void readSerialInput();
void parseCommand(char* packet);
void checkHeartbeat();
void applyCameraServo(int position);

// --- CONFIGURATION ---
const unsigned long HEARTBEAT_TIMEOUT_MS = 200;
const size_t SERIAL_BUF_SIZE = 32;

// Geared DC motors need a minimum duty cycle to overcome static friction.
// Below this the coils buzz/hum without turning. Tune 70-95 to your motors.
const int MIN_MOVE_PWM = 150;

// ELEGOO Smart Robot Car V4.0 pin assignments (from DeviceDriverSet_xxx0.h)
// Motor A (Right): PWMA=5, AIN_1=7
// Motor B (Left):  PWMB=6, BIN_1=8
// STBY=3
const uint8_t RIGHT_SPEED_PIN = 5;  // PWMA (Motor A)
const uint8_t RIGHT_DIR_PIN = 7;    // AIN_1 (Motor A direction)
const uint8_t LEFT_SPEED_PIN = 6;   // PWMB (Motor B)
const uint8_t LEFT_DIR_PIN = 8;     // BIN_1 (Motor B direction)
const uint8_t STBY_PIN = 3;         // STBY pin (ELEGOO uses pin 3)
const uint8_t MY_ROBOT_SERVO_PIN = 10; // Servo pin (avoid conflict with STBY on pin 3)
const int CAMERA_SERVO_CENTER = 90;

Servo cameraServo;

char serialBuffer[SERIAL_BUF_SIZE];
size_t bufferIndex = 0;
bool bufferInProgress = false;

// Independent motor tracking for the heartbeat
bool motor1Active = false;
bool motor2Active = false;
unsigned long lastCommandTime = 0;

void setup() {
  Serial.begin(115200);
  wdt_enable(WDTO_500MS);

  // ELEGOO motor driver pin configuration
  pinMode(LEFT_SPEED_PIN, OUTPUT);
  pinMode(LEFT_DIR_PIN, OUTPUT);
  pinMode(RIGHT_SPEED_PIN, OUTPUT);
  pinMode(RIGHT_DIR_PIN, OUTPUT);
  pinMode(STBY_PIN, OUTPUT);
  digitalWrite(STBY_PIN, HIGH); // Force motor driver awake

  stopMotors();

  cameraServo.attach(MY_ROBOT_SERVO_PIN);
  cameraServo.write(CAMERA_SERVO_CENTER);

  lastCommandTime = millis();
  Serial.println("UNO READY");
}

void loop() {
  wdt_reset();
  checkHeartbeat();
  readSerialInput();
}

// --- FUNCTION DEFINITIONS ---
void stopMotors() {
  // ELEGOO single-pin control: direction pin LOW = stop/brake
  digitalWrite(LEFT_DIR_PIN, LOW);
  analogWrite(LEFT_SPEED_PIN, 0);

  digitalWrite(RIGHT_DIR_PIN, LOW);
  analogWrite(RIGHT_SPEED_PIN, 0);

  // Keep state synced with hardware
  motor1Active = false;
  motor2Active = false;
}

void setMotor(int motorId, char dir, int speed) {
  uint8_t speedPin, dirPin;

  if (motorId == 1) { // Motor 1 = Right (Motor A)
    speedPin = RIGHT_SPEED_PIN;
    dirPin = RIGHT_DIR_PIN;
  } else if (motorId == 2) { // Motor 2 = Left (Motor B)
    speedPin = LEFT_SPEED_PIN;
    dirPin = LEFT_DIR_PIN;
  } else {
    return;
  }

  bool isMoving = false;

  // ELEGOO single-pin control: LOW = forward, HIGH = backward (directions flipped for correct movement)
  if (dir == 'F') {
    if (speed > 0 && speed < MIN_MOVE_PWM) speed = MIN_MOVE_PWM;
    digitalWrite(dirPin, LOW);    // Forward (flipped for correct movement)
    analogWrite(speedPin, speed);
    isMoving = true;
  } else if (dir == 'B') {
    if (speed > 0 && speed < MIN_MOVE_PWM) speed = MIN_MOVE_PWM;
    digitalWrite(dirPin, HIGH);   // Backward (flipped for correct movement)
    analogWrite(speedPin, speed);
    isMoving = true;
  } else { // Stop
    digitalWrite(dirPin, LOW);
    analogWrite(speedPin, 0);
    isMoving = false;
  }

  // Sync specific motor state
  if (motorId == 1) motor1Active = isMoving;
  if (motorId == 2) motor2Active = isMoving;
}

void readSerialInput() {
  while (Serial.available() > 0) {
    char incomingChar = Serial.read();

    if (incomingChar == '<') {
      bufferInProgress = true;
      bufferIndex = 0;
    } else if (incomingChar == '>') {
      bufferInProgress = false;
      serialBuffer[bufferIndex] = '\0'; // Safely terminate the string
      parseCommand(serialBuffer);
      lastCommandTime = millis();
    } else if (bufferInProgress && bufferIndex < SERIAL_BUF_SIZE - 1) {
      serialBuffer[bufferIndex++] = incomingChar;
    }
  }
}

void parseCommand(char* packet) {
  if (packet == NULL || packet[0] == '\0') return;

  char* token = strtok(packet, ",");
  if (token == NULL) return;

  if (strcmp(token, "SERVO") == 0) {
    token = strtok(NULL, ",");
    if (token != NULL) {
      applyCameraServo(atoi(token));
    }
    return;
  }

  int motorId = atoi(token);
  token = strtok(NULL, ",");
  if (token == NULL) return;
  char dir = token[0];

  token = strtok(NULL, ",");
  if (token == NULL) return;
  int speedVal = constrain(atoi(token), 0, 255);

  setMotor(motorId, dir, speedVal);
}

void applyCameraServo(int position) {
  cameraServo.write(constrain(position, 0, 180));
}

void checkHeartbeat() {
  if ((motor1Active || motor2Active) && (millis() - lastCommandTime > HEARTBEAT_TIMEOUT_MS)) {
    stopMotors();
  }
}
