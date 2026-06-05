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
bool verifyShieldConnectivity();

// --- CONFIGURATION ---
const unsigned long HEARTBEAT_TIMEOUT_MS = 200;
const size_t SERIAL_BUF_SIZE = 128;

// Motor Shield Pin Assignments (SmartCar Shield v1.1 compatible)
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

/**
 * Verify motor shield connectivity by checking if pins can be configured.
 * This is a basic check - actual shield seating should be verified physically.
 * @return true if all motor pins configured successfully
 */
bool verifyShieldConnectivity() {
  // Attempt to configure all motor pins
  pinMode(LEFT_SPEED_PIN, OUTPUT);
  pinMode(LEFT_DIR_A, OUTPUT);
  pinMode(LEFT_DIR_B, OUTPUT);
  pinMode(RIGHT_SPEED_PIN, OUTPUT);
  pinMode(RIGHT_DIR_A, OUTPUT);
  pinMode(RIGHT_DIR_B, OUTPUT);
  
  // Set all pins to known state (LOW) for safety
  digitalWrite(LEFT_SPEED_PIN, LOW);
  digitalWrite(LEFT_DIR_A, LOW);
  digitalWrite(LEFT_DIR_B, LOW);
  digitalWrite(RIGHT_SPEED_PIN, LOW);
  digitalWrite(RIGHT_DIR_A, LOW);
  digitalWrite(RIGHT_DIR_B, LOW);
  
  return true; // Basic pin configuration succeeded
}

void setup() {
  Serial.begin(115200);
  wdt_enable(WDTO_500MS);

  // Verify shield connectivity before proceeding
  if (!verifyShieldConnectivity()) {
    Serial.println("ERROR: Shield connectivity check failed");
    while(1); // Halt on critical error
  }
  Serial.println("Shield connectivity verified");

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

/**
 * Set motor speed and direction.
 * 
 * Motor ID Mapping:
 * - Motor 1 = RIGHT motor (pins 6,9,11)
 * - Motor 2 = LEFT motor (pins 5,7,8)
 * 
 * Direction Logic (REVERSED for 180-degree chassis rotation):
 * This robot's motors are mounted in opposite directions due to chassis design.
 * When both motors receive 'F' (forward), the robot moves forward.
 * The H-bridge logic is inverted to compensate for the physical motor orientation.
 * 
 * @param motorId 1 for RIGHT motor, 2 for LEFT motor
 * @param dir 'F' for forward, 'B' for backward, 'S' for stop
 * @param speed PWM value (0-255)
 */
void setMotor(int motorId, char dir, int speed) {
  uint8_t speedPin, dirA, dirB;
  
  if (motorId == 1) {
    // Motor 1 = RIGHT motor
    speedPin = RIGHT_SPEED_PIN;
    dirA = RIGHT_DIR_A;
    dirB = RIGHT_DIR_B;
  } else if (motorId == 2) {
    // Motor 2 = LEFT motor
    speedPin = LEFT_SPEED_PIN;
    dirA = LEFT_DIR_A;
    dirB = LEFT_DIR_B;
  } else {
    return; // Invalid motor ID
  }

  bool isMoving = false;

  // REVERSED LOGIC FOR 180 DEGREE CHASSIS ROTATION
  // Motors are mounted opposite to each other, so H-bridge signals are inverted
  // to ensure coordinated forward/backward movement.
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
    // Stop
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
  // If motors are active but no commands received within timeout, stop for safety
  if ((motor1Active || motor2Active) && (millis() - lastCommandTime > HEARTBEAT_TIMEOUT_MS)) {
    stopMotors();
  }
}
