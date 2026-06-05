# Hardware Safety & Wiring Notes

## Reference layout

```
┌─────────────────────────────────────────────┐
│  Rock64 SBC                                 │
│    USB-A 2.0 ──(USB-B)──► Arduino Uno R3    │
│    USB-A 2.0 ──(USB-C)──► ESP32-S3 (opt.)   │
│    USB-A 3.0 ──► WiFi adapter               │
│    DC 3.5mm  ◄── 5V 3A power bank           │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│  Arduino Uno R3 (bottom)                    │
│  Smart Car Shield v1.1 (stacked on top)     │
│    ├── Motor cables (L/R drive)             │
│    ├── MPU6050 (dedicated I2C slot)         │
│    ├── Ultrasonic sensor (4-pin HC-SR04)    │
│    ├── Servo (ultrasonic pan) → servo port  │
│    ├── ESP32-S3 → 4-pin UART slot           │
│    └── VIN/GND ◄── SmartCar v4 battery      │
└─────────────────────────────────────────────┘
```

## Critical safety items

### 1. USB power backfeed — use a data-only cable

The Arduino Uno gets power through two paths simultaneously:

- **Battery → Shield VIN** (motor + logic power)
- **USB-B → Rock64** (host communication)

Without protection this can backfeed 5V from the battery into the
Rock64's USB port, or draw conflicting currents from both sources.

**Fix**: Use a **data-only USB cable** (no +5V wire) for the
Arduino-to-Rock64 connection.  If you don't have one, open a spare
USB-B cable and cut or tape the **red wire** (pin 1 / VBUS).  The black
(GND), green (D+), and white (D−) wires must remain connected.

### 2. UART logic levels — add a level shifter

The ESP32-S3 runs on **3.3V logic**.  The Arduino Uno R3 runs on **5V
logic**.  The 4-pin UART slot on the Smart Car Shield likely passes 5V
TX directly to the ESP32 RX pin.

**Risk**: A 5V signal into a 3.3V GPIO can permanently damage the
ESP32-S3.

**Fix**: Place a **bidirectional logic level shifter** (e.g. BSS138 or
TXB0104 module) between the shield's UART TX/RX and the ESP32.  Connect
the 5V side to the shield and the 3.3V side to the ESP32.

Alternatively, a simple resistive voltage divider (1kΩ + 2kΩ) on the
5V TX line is sufficient for unidirectional (Arduino → ESP32) data.

### 3. Motor noise — protect sensors

DC motors generate electrical noise (back-EMF spikes) that can corrupt
I2C and analog sensor readings.

**Symptoms**: MPU6050 returning NaN / erratic values, ultrasonic sensor
giving wildly wrong distances, random ESP32 resets.

**Fixes**:
- Add **100nF ceramic capacitors** across each motor's terminals.
- Add a **100μF electrolytic capacitor** on the 5V/3.3V rail near the
  MPU6050 and ultrasonic sensor.
- Route sensor wires **away from motor wires** — don't bundle them
  together.
- If the shield has a dedicated servo power rail, use it; otherwise add
  a separate BEC (battery eliminator circuit) for the servo to avoid
  voltage dips when motors stall.

### 4. Common ground

All devices must share a **common ground reference**:

- Battery GND → Shield GND
- Shield GND → Arduino GND (via stacking headers — automatic)
- Arduino GND → Rock64 GND (via USB cable — automatic if data-only
  cable still has GND connected)
- ESP32 GND → Shield GND (via the 4-pin UART slot — verify this)

If grounds are not connected, serial communication will be unreliable
(garbled bytes, random disconnects).

### 5. Power budget

| Device | Typical draw | Source |
|--------|-------------|--------|
| Rock64 | 500mA–1.5A | 5V 3A power bank |
| Arduino Uno + shield | 200mA idle | Battery via VIN |
| 4× DC motors (stall) | 2–4A total | Battery via shield H-bridge |
| ESP32-S3 (WiFi + camera) | 200–350mA | Shield 3.3V or USB-C |
| Servo (SG90) | 150–500mA | Shield servo rail |
| MPU6050 | 5mA | Shield I2C 5V |
| HC-SR04 ultrasonic | 15mA | Shield 5V |

Ensure the SmartCar v4 battery can sustain at least **3A continuous**
for motors + all logic.  If using NiMH AA cells, they may sag under
heavy motor load — consider a LiPo pack with a proper BMS.

### 6. ESP32-S3 USB-C to Rock64

The ESP32-S3 has a USB-C port that can optionally connect to the Rock64's
second USB-A 2.0 port.  This is **not currently needed** — the ESP32
communicates via WiFi (camera stream) and UART (motor relay from shield).

The USB-C connection would be useful for:
- Flashing new firmware from the Rock64 instead of a PC
- Serial debug logging (`Serial.println` output)
- Future USB-CDC data channel

If you connect it, the same backfeed caution applies: use a data-only
cable unless the ESP32 should be powered from the Rock64.
