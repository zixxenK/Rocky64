#include <Arduino.h>
#include <Servo.h>
#include <avr/wdt.h>
#include <EEPROM.h>
#include <string.h>
#include <stdlib.h>

// --- FORWARD DECLARATIONS (Fixes "not declared in this scope" errors) ---
void stopMotors();
void setMotor(int motorId, char dir, int speed);
void readSerialInput();
void parseCommand(char* packet);
void checkHeartbeat();
void applyCameraServo(int position);
int readUltrasonicDistance();
void updateUltrasonicTelemetry();
void loadConfig();
void saveConfig();
void resetConfig();
void handleConfigCommand(char* packet);
void updateServoScan();

// --- CONFIGURATION ---
const unsigned long HEARTBEAT_TIMEOUT_MS = 200;
const size_t SERIAL_BUF_SIZE = 32;

// Geared DC motors need a minimum duty cycle to overcome static friction.
// Below this the coils buzz/hum without turning. Tune 70-95 to your motors.
const int DEFAULT_MIN_MOVE_PWM = 100;
int MIN_MOVE_PWM = 100;

// Global speed limit (reduced from 255 to 180 for safer operation)
const int DEFAULT_MAX_SPEED = 180;
int MAX_SPEED = 180;

// Ultrasonic sensor configuration (SmartCar Shield v1.1 pinout)
const uint8_t ULTRASONIC_TRIG_PIN = 13;
const uint8_t ULTRASONIC_ECHO_PIN = 12;
const unsigned long ULTRASONIC_UPDATE_INTERVAL_MS = 100; // Update every 100ms
const int DEFAULT_EMERGENCY_STOP_DISTANCE_CM = 10; // Stop if obstacle within 10cm
int EMERGENCY_STOP_DISTANCE_CM = 10;

// ELEGOO Smart Robot Car V4.0 pin assignments (from DeviceDriverSet_xxx0.h)
// Motor A (Right): PWMA=5, AIN_1=7
// Motor B (Left):  PWMB=6, BIN_1=8
// STBY=3
const uint8_t RIGHT_SPEED_PIN = 5;  // PWMA (Motor A)
const uint8_t RIGHT_DIR_PIN = 7;    // AIN_1 (Motor A direction)
const uint8_t LEFT_SPEED_PIN = 6;   // PWMB (Motor B)
const uint8_t LEFT_DIR_PIN = 8;     // BIN_1 (Motor B direction)
const uint8_t STBY_PIN = 3;         // STBY pin (ELEGOO uses pin 3)

// --- CONFIGURATION STRUCTURES ---
struct MotorConfig {
  int minSpeed;
  int maxSpeed;
  bool invertDirection;
};

struct SafetyConfig {
  int stopDistance;
  int warningDistance;
  int maxSpeedLimit;
};

struct ServoConfig {
  int scanRange;
  int scanSpeed;
};

// Global configuration
MotorConfig motorConfig[2];  // [0] = Motor 1 (Right), [1] = Motor 2 (Left)
SafetyConfig safetyConfig;
ServoConfig servoConfig;

// EEPROM addresses
#define EEPROM_MAGIC 0xA5
#define EEPROM_MAGIC_ADDR 0
#define EEPROM_CONFIG_START 1
#define EEPROM_CONFIG_SIZE sizeof(motorConfig) + sizeof(safetyConfig) + sizeof(servoConfig)

// Servo pin - can be overridden with build flag -DCAMERA_SERVO_PIN=X
#ifndef CAMERA_SERVO_PIN
#define CAMERA_SERVO_PIN 10
#endif
const uint8_t MY_ROBOT_SERVO_PIN = CAMERA_SERVO_PIN;
const int CAMERA_SERVO_CENTER = 90;

Servo cameraServo;

char serialBuffer[SERIAL_BUF_SIZE];
size_t bufferIndex = 0;
bool bufferInProgress = false;

// Independent motor tracking for the heartbeat
bool motor1Active = false;
bool motor2Active = false;
unsigned long lastCommandTime = 0;

// Ultrasonic sensor state
unsigned long lastUltrasonicUpdate = 0;
int currentDistanceCm = 0;

// Servo scanning state
bool servoScanning = false;
int servoScanDirection = 1;
unsigned long lastServoScanUpdate = 0;
int currentServoPosition = CAMERA_SERVO_CENTER;

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

  // Ultrasonic sensor pin configuration
  pinMode(ULTRASONIC_TRIG_PIN, OUTPUT);
  pinMode(ULTRASONIC_ECHO_PIN, INPUT);
  digitalWrite(ULTRASONIC_TRIG_PIN, LOW);

  // Load configuration from EEPROM
  loadConfig();

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
  updateUltrasonicTelemetry();
  updateServoScan();
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
  int configIndex = motorId - 1;  // Convert to 0-based index

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

  // Apply motor-specific configuration
  int minSpeed = motorConfig[configIndex].minSpeed;
  int maxSpeed = motorConfig[configIndex].maxSpeed;
  bool invertDir = motorConfig[configIndex].invertDirection;

  // Clamp speed to configured limits
  speed = constrain(speed, 0, maxSpeed);

  // ELEGOO single-pin control: LOW = forward, HIGH = backward
  if (dir == 'F') {
    if (speed > 0 && speed < minSpeed) speed = minSpeed;
    if (invertDir) dir = 'B';
    digitalWrite(dirPin, LOW);    // Forward
    analogWrite(speedPin, speed);
    isMoving = true;
  } else if (dir == 'B') {
    if (speed > 0 && speed < minSpeed) speed = minSpeed;
    if (invertDir) dir = 'F';
    digitalWrite(dirPin, HIGH);   // Backward
    analogWrite(speedPin, speed);
    isMoving = true;
  } else { // Stop
    digitalWrite(dirPin, LOW);
    analogWrite(speedPin, 0);
    isMoving = false;
  }

  // Debug: output actual pin states
  Serial.print("<DBG,M");
  Serial.print(motorId);
  Serial.print(",pin=");
  Serial.print(speedPin);
  Serial.print(",spd=");
  Serial.print(speed);
  Serial.print(",dir=");
  Serial.print(dirPin);
  Serial.print(",");
  Serial.print(digitalRead(dirPin) ? "HIGH" : "LOW");
  Serial.println(">");

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

  if (strcmp(token, "CONFIG") == 0) {
    handleConfigCommand(packet);
    return;
  }

  int motorId = atoi(token);
  token = strtok(NULL, ",");
  if (token == NULL) return;
  char dir = token[0];

  token = strtok(NULL, ",");
  if (token == NULL) return;
  int speedVal = constrain(atoi(token), 0, MAX_SPEED);

  // Debug: echo received command
  Serial.print("<ACK,M");
  Serial.print(motorId);
  Serial.print(",");
  Serial.print(dir);
  Serial.print(",");
  Serial.print(speedVal);
  Serial.println(">");

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

int readUltrasonicDistance() {
  // Send a 10 microsecond pulse to trigger the sensor
  digitalWrite(ULTRASONIC_TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(ULTRASONIC_TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(ULTRASONIC_TRIG_PIN, LOW);

  // Read the echo pulse duration (timeout at 30ms for ~5m max distance)
  long duration = pulseIn(ULTRASONIC_ECHO_PIN, HIGH, 30000);

  // Convert to distance in cm (speed of sound = 343 m/s)
  // Distance = (duration * speed of sound) / 2
  // Distance in cm = (duration * 0.0343) / 2 = duration * 0.01715
  int distance = duration * 0.01715;

  // Return 0 if timeout (no echo received)
  if (distance == 0 || distance > 400) {
    return 0;
  }

  return distance;
}

void updateUltrasonicTelemetry() {
  unsigned long now = millis();

  // Update ultrasonic reading at fixed interval
  if (now - lastUltrasonicUpdate >= ULTRASONIC_UPDATE_INTERVAL_MS) {
    lastUltrasonicUpdate = now;
    currentDistanceCm = readUltrasonicDistance();

    // Publish distance telemetry
    Serial.print("<DISTANCE,");
    Serial.print(currentDistanceCm);
    Serial.println(">");

    // Emergency stop if obstacle is too close
    if (currentDistanceCm > 0 && currentDistanceCm < safetyConfig.stopDistance) {
      if (motor1Active || motor2Active) {
        stopMotors();
        Serial.print("<ALERT,OBSTACLE,");
        Serial.print(currentDistanceCm);
        Serial.println(">");
      }
    }
  }
}

// --- CONFIGURATION MANAGEMENT ---

void loadConfig() {
  // Check if EEPROM has valid config
  uint8_t magic = EEPROM.read(EEPROM_MAGIC_ADDR);
  if (magic != EEPROM_MAGIC) {
    // No valid config, use defaults
    resetConfig();
    Serial.println("<CONFIG,LOAD,DEFAULT>");
    return;
  }

  // Load config from EEPROM
  EEPROM.get(EEPROM_CONFIG_START, motorConfig);
  EEPROM.get(EEPROM_CONFIG_START + sizeof(motorConfig), safetyConfig);
  EEPROM.get(EEPROM_CONFIG_START + sizeof(motorConfig) + sizeof(safetyConfig), servoConfig);

  // Apply loaded config to runtime variables
  MIN_MOVE_PWM = motorConfig[0].minSpeed;
  MAX_SPEED = safetyConfig.maxSpeedLimit;
  EMERGENCY_STOP_DISTANCE_CM = safetyConfig.stopDistance;

  Serial.println("<CONFIG,LOAD,SUCCESS>");
}

void saveConfig() {
  // Write magic byte
  EEPROM.write(EEPROM_MAGIC_ADDR, EEPROM_MAGIC);

  // Save config to EEPROM
  EEPROM.put(EEPROM_CONFIG_START, motorConfig);
  EEPROM.put(EEPROM_CONFIG_START + sizeof(motorConfig), safetyConfig);
  EEPROM.put(EEPROM_CONFIG_START + sizeof(motorConfig) + sizeof(safetyConfig), servoConfig);

  Serial.println("<CONFIG,SAVE,SUCCESS>");
}

void resetConfig() {
  // Reset motor configs
  for (int i = 0; i < 2; i++) {
    motorConfig[i].minSpeed = DEFAULT_MIN_MOVE_PWM;
    motorConfig[i].maxSpeed = DEFAULT_MAX_SPEED;
    motorConfig[i].invertDirection = false;
  }

  // Reset safety config
  safetyConfig.stopDistance = DEFAULT_EMERGENCY_STOP_DISTANCE_CM;
  safetyConfig.warningDistance = 30;  // 30cm warning distance
  safetyConfig.maxSpeedLimit = DEFAULT_MAX_SPEED;

  // Reset servo config
  servoConfig.scanRange = 90;  // 45 degrees left to 45 degrees right
  servoConfig.scanSpeed = 20;  // 20ms per degree

  // Apply to runtime variables
  MIN_MOVE_PWM = DEFAULT_MIN_MOVE_PWM;
  MAX_SPEED = DEFAULT_MAX_SPEED;
  EMERGENCY_STOP_DISTANCE_CM = DEFAULT_EMERGENCY_STOP_DISTANCE_CM;

  Serial.println("<CONFIG,RESET,SUCCESS>");
}

void handleConfigCommand(char* packet) {
  char* token = strtok(packet, ",");
  if (token == NULL) return;
  
  // Skip "CONFIG" token
  token = strtok(NULL, ",");
  if (token == NULL) return;

  if (strcmp(token, "SAVE") == 0) {
    saveConfig();
    return;
  }

  if (strcmp(token, "LOAD") == 0) {
    loadConfig();
    return;
  }

  if (strcmp(token, "RESET") == 0) {
    resetConfig();
    return;
  }

  // Motor configuration: CONFIG,MOTOR1,MIN_SPEED,value
  if (strncmp(token, "MOTOR", 5) == 0) {
    int motorId = atoi(token + 5) - 1;  // Convert to 0-based index
    if (motorId < 0 || motorId >= 2) return;

    token = strtok(NULL, ",");
    if (token == NULL) return;

    if (strcmp(token, "MIN_SPEED") == 0) {
      token = strtok(NULL, ",");
      if (token != NULL) {
        motorConfig[motorId].minSpeed = atoi(token);
        MIN_MOVE_PWM = motorConfig[0].minSpeed;
        Serial.print("<CONFIG,MOTOR");
        Serial.print(motorId + 1);
        Serial.print(",MIN_SPEED,");
        Serial.println(motorConfig[motorId].minSpeed);
      }
    } else if (strcmp(token, "MAX_SPEED") == 0) {
      token = strtok(NULL, ",");
      if (token != NULL) {
        motorConfig[motorId].maxSpeed = atoi(token);
        Serial.print("<CONFIG,MOTOR");
        Serial.print(motorId + 1);
        Serial.print(",MAX_SPEED,");
        Serial.println(motorConfig[motorId].maxSpeed);
      }
    } else if (strcmp(token, "INVERT") == 0) {
      token = strtok(NULL, ",");
      if (token != NULL) {
        motorConfig[motorId].invertDirection = (strcmp(token, "true") == 0);
        Serial.print("<CONFIG,MOTOR");
        Serial.print(motorId + 1);
        Serial.print(",INVERT,");
        Serial.println(motorConfig[motorId].invertDirection ? "true" : "false");
      }
    }
    return;
  }

  // Safety configuration
  if (strcmp(token, "SAFETY") == 0) {
    token = strtok(NULL, ",");
    if (token == NULL) return;

    if (strcmp(token, "STOP_DIST") == 0) {
      token = strtok(NULL, ",");
      if (token != NULL) {
        safetyConfig.stopDistance = atoi(token);
        EMERGENCY_STOP_DISTANCE_CM = safetyConfig.stopDistance;
        Serial.print("<CONFIG,SAFETY,STOP_DIST,");
        Serial.println(safetyConfig.stopDistance);
      }
    } else if (strcmp(token, "MAX_SPEED") == 0) {
      token = strtok(NULL, ",");
      if (token != NULL) {
        safetyConfig.maxSpeedLimit = atoi(token);
        MAX_SPEED = safetyConfig.maxSpeedLimit;
        Serial.print("<CONFIG,SAFETY,MAX_SPEED,");
        Serial.println(safetyConfig.maxSpeedLimit);
      }
    }
    return;
  }

  // Servo configuration
  if (strcmp(token, "SERVO") == 0) {
    token = strtok(NULL, ",");
    if (token == NULL) return;

    if (strcmp(token, "SCAN_RANGE") == 0) {
      token = strtok(NULL, ",");
      if (token != NULL) {
        servoConfig.scanRange = atoi(token);
        Serial.print("<CONFIG,SERVO,SCAN_RANGE,");
        Serial.println(servoConfig.scanRange);
      }
    }
    return;
  }
}

void updateServoScan() {
  if (!servoScanning) return;

  unsigned long now = millis();
  if (now - lastServoScanUpdate >= (unsigned long)servoConfig.scanSpeed) {
    lastServoScanUpdate = now;

    // Update servo position
    currentServoPosition += servoScanDirection;

    // Reverse direction at limits
    int halfRange = servoConfig.scanRange / 2;
    if (currentServoPosition >= CAMERA_SERVO_CENTER + halfRange) {
      servoScanDirection = -1;
    } else if (currentServoPosition <= CAMERA_SERVO_CENTER - halfRange) {
      servoScanDirection = 1;
    }

    cameraServo.write(currentServoPosition);
  }
}
