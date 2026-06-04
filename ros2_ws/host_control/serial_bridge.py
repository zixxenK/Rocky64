import glob
import os
import serial
from serial import SerialException


def _select_serial_port(port: str) -> str:
    if port and os.path.exists(port):
        return port

    candidates = []
    for pattern in ['/dev/ttyACM*', '/dev/ttyUSB*']:
        candidates.extend(sorted(glob.glob(pattern)))

    if candidates:
        print(
            f'Configured serial port {port} not found. Auto-selecting {candidates[0]} from {candidates}'
        )
        return candidates[0]

    return port


class TelemetrySerialBridge:
    def __init__(self, port="/dev/ttyACM0", baudrate=115200, timeout=0.05):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.connection = None
        self.open()

    def open(self):
        self.port = _select_serial_port(self.port)
        try:
            self.connection = serial.Serial(
                self.port,
                self.baudrate,
                timeout=self.timeout,
            )
            self.connection.reset_input_buffer()
            self.connection.reset_output_buffer()
        except SerialException as exc:
            raise RuntimeError(
                f"Unable to open serial port {self.port}: {exc}"
            ) from exc

    def send_motor_command(self, motor_id: int, direction: str, speed: int):
        constrained_speed = max(0, min(255, int(speed)))
        run_direction = direction.upper() if direction else "S"
        if run_direction not in {"F", "B", "S"}:
            raise ValueError("direction must be 'F', 'B', or 'S'")

        command_packet = f"<{motor_id},{run_direction},{constrained_speed}>\n"
        self.connection.write(command_packet.encode("utf-8"))
        self.connection.flush()

    def send_emergency_stop(self):
        self.send_motor_command(1, "S", 0)
        self.send_motor_command(2, "S", 0)

    def close(self):
        if self.connection and self.connection.is_open:
            try:
                self.send_emergency_stop()
            except (SerialException, RuntimeError):
                pass
            self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
