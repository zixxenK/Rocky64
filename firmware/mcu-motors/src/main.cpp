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

const uint8_t LEFT_SPEED_PIN = 5; 
const uint8_t LEFT_DIR_A = 7;     
const uint8_t LEFT_DIR_B = 8;     
const uint8_t RIGHT_SPEED_PIN = 6;
const uint8_t RIGHT_DIR_A = 9;    
const uint8_t RIGHT_DIR_B = 11;   

const uint8_t MY_ROBOT_SERVO_PIN = 3; 
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

  pinMode(LEFT_SPEED_PIN, OUTPUT);
  pinMode(LEFT_DIR_A, OUTPUT);
  pinMode(LEFT_DIR_B, OUTPUT);
  
  pinMode(RIGHT_SPEED_PIN, OUTPUT);
  pinMode(RIGHT_DIR_A, OUTPUT);
  pinMode(RIGHT_DIR_B, OUTPUT);

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
  digitalWrite(LEFT_DIR_A, LOW);
  digitalWrite(LEFT_DIR_B, LOW);
  analogWrite(LEFT_SPEED_PIN, 0);

  digitalWrite(RIGHT_DIR_A, LOW);
  digitalWrite(RIGHT_DIR_B, LOW);
  analogWrite(RIGHT_SPEED_PIN, 0);

  // Keep state synced with hardware
  motor1Active = false;
  motor2Active = false;
}

void setMotor(int motorId, char dir, int speed) {
  uint8_t speedPin, dirA, dirB;
  
  if (motorId == 1) {
    speedPin = RIGHT_SPEED_PIN;
    dirA = RIGHT_DIR_A;
    dirB = RIGHT_DIR_B;
  } else if (motorId == 2) {
    speedPin = LEFT_SPEED_PIN;
    dirA = LEFT_DIR_A;
    dirB = LEFT_DIR_B;
  } else {
    return;
  }

  bool isMoving = false;

  // --- REVERSED LOGIC FOR 180 DEGREE CHASSIS ROTATION ---
  if (dir == 'F') { 
    digitalWrite(dirA, LOW);   
    digitalWrite(dirB, HIGH);  
    analogWrite(speedPin, speed);
    isMoving = true;
  } else if (dir == 'B') { 
    digitalWrite(dirA, HIGH);  
    digitalWrite(dirB, LOW);   
    analogWrite(speedPin, speed);
    isMoving = true;
  } else { 
    digitalWrite(dirA, LOW);
    digitalWrite(dirB, LOW);
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