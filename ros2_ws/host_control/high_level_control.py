import threading
import time
from typing import Optional

import serial
import serial.serialutil


class TelemetryPacket:
    def __init__(self, gyro_x: int, gyro_y: int, gyro_z: int, accel_x: int, accel_y: int, accel_z: int):
        self.gyro_x = gyro_x
        self.gyro_y = gyro_y
        self.gyro_z = gyro_z
        self.accel_x = accel_x
        self.accel_y = accel_y
        self.accel_z = accel_z

    def __str__(self) -> str:
        return (
            f"TELEMETRY gyro=({self.gyro_x},{self.gyro_y},{self.gyro_z}) "
            f"accel=({self.accel_x},{self.accel_y},{self.accel_z})"
        )


class SerialRobotController:
    def __init__(self, port: str = "/dev/ttyS2", baudrate: int = 9600, timeout: float = 0.1):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._lock = threading.Lock()
        self._serial: Optional[serial.Serial] = None
        self._reader_thread = None
        self._running = False

    def connect(self) -> None:
        self._serial = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
        self._running = True
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()
        print(f"Connected to serial port {self.port} @ {self.baudrate}")

    def close(self) -> None:
        self._running = False
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1.0)
        if self._serial and self._serial.is_open:
            self._serial.close()
            print("Serial port closed")

    def send_motor_command(self, left_speed: int, right_speed: int) -> None:
        left_speed = max(-255, min(255, left_speed))
        right_speed = max(-255, min(255, right_speed))
        command = f"<MOVE,{left_speed},{right_speed}>"
        with self._lock:
            if self._serial and self._serial.is_open:
                self._serial.write(command.encode("utf-8"))
                self._serial.flush()
                print(f"Sent command: {command}")
            else:
                raise RuntimeError("Serial port is not open")

    def _read_loop(self) -> None:
        buffer = ""
        while self._running and self._serial and self._serial.is_open:
            try:
                line = self._serial.readline().decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                if line.startswith("TELEMETRY,"):
                    packet = self._parse_telemetry(line)
                    if packet:
                        print(packet)
                else:
                    print(f"Unknown serial line: {line}")
            except serial.SerialException as exc:
                print(f"Serial exception: {exc}")
                break
            except Exception as exc:
                print(f"Unexpected read error: {exc}")
                continue

    def _parse_telemetry(self, line: str) -> Optional[TelemetryPacket]:
        parts = line.split(",")
        if len(parts) != 7:
            print(f"Malformed telemetry packet: {line}")
            return None

        try:
            gyro_x = int(parts[1])
            gyro_y = int(parts[2])
            gyro_z = int(parts[3])
            accel_x = int(parts[4])
            accel_y = int(parts[5])
            accel_z = int(parts[6])
        except ValueError:
            print(f"Telemetry packet contains invalid integers: {line}")
            return None

        return TelemetryPacket(gyro_x, gyro_y, gyro_z, accel_x, accel_y, accel_z)

    def send_stop(self) -> None:
        self.send_motor_command(0, 0)


def print_instructions() -> None:
    print("Enter one of the following commands:")
    print("  f: forward")
    print("  b: backward")
    print("  l: left")
    print("  r: right")
    print("  s: stop")
    print("  q: quit")


def main() -> None:
    controller = SerialRobotController()
    try:
        controller.connect()
    except serial.SerialException as exc:
        print(f"Unable to open serial port: {exc}")
        return

    try:
        print_instructions()
        while True:
            command = input("> ").strip().lower()
            if command == "q":
                break
            if command == "f":
                controller.send_motor_command(200, 200)
            elif command == "b":
                controller.send_motor_command(-200, -200)
            elif command == "l":
                controller.send_motor_command(-150, 150)
            elif command == "r":
                controller.send_motor_command(150, -150)
            elif command == "s":
                controller.send_stop()
            else:
                print("Unknown command")
    except KeyboardInterrupt:
        print("Keyboard interrupt received")
    finally:
        controller.send_stop()
        controller.close()


if __name__ == "__main__":
    main()
