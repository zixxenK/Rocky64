import threading
import time
from typing import Optional, Tuple

import cv2
import rclpy
import serial
from geometry_msgs.msg import Twist
from rclpy.node import Node
from serial import SerialException
from std_msgs.msg import String


class CameraStreamMonitor:
    def __init__(self, ip_address: str, port: int = 80, path: str = '/stream'):
        self.stream_url = f'http://{ip_address}:{port}{path}'
        self.capture = cv2.VideoCapture(self.stream_url)
        self.grabbed = False
        self.frame_size = (0, 0)
        self.active = False
        self.lock = threading.Lock()
        self.thread: Optional[threading.Thread] = None

        if not self.capture.isOpened():
            raise RuntimeError(f'Unable to open camera stream: {self.stream_url}')

        self.active = True
        self.thread = threading.Thread(target=self._update_buffer, daemon=True)
        self.thread.start()

    def _update_buffer(self) -> None:
        while self.active:
            grabbed, frame = self.capture.read()
            if not grabbed:
                time.sleep(0.05)
                continue

            with self.lock:
                self.grabbed = grabbed
                self.frame_size = (frame.shape[1], frame.shape[0])

    def get_status(self) -> Tuple[bool, Tuple[int, int]]:
        with self.lock:
            return self.grabbed, self.frame_size

    def stop(self) -> None:
        self.active = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        self.capture.release()


class SerialRobotController(Node):
    def __init__(
        self,
        port: str = '/dev/ttyS1',
        baudrate: int = 115200,
        timeout: float = 0.1,
        camera_ip: str = '192.168.4.1',
        camera_port: int = 80,
    ):
        super().__init__('robot_control_node')
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.camera_ip = camera_ip
        self.camera_port = camera_port

        self._serial: Optional[serial.Serial] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._running = False
        self.camera_monitor: Optional[CameraStreamMonitor] = None

        self.telemetry_publisher = self.create_publisher(String, 'robot_telemetry', 10)
        self.camera_status_publisher = self.create_publisher(String, 'camera_status', 10)
        self.create_subscription(Twist, 'cmd_vel', self.cmd_vel_callback, 10)
        self.create_timer(1.0, self._publish_status)

        self._connect_serial()
        self._connect_camera()

    def _connect_serial(self) -> None:
        try:
            self._serial = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            self._running = True
            self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
            self._reader_thread.start()
            self.get_logger().info(f'Connected to serial port {self.port} @ {self.baudrate}')
        except SerialException as exc:
            self._serial = None
            self.get_logger().error(f'Unable to open serial port {self.port}: {exc}')

    def _connect_camera(self) -> None:
        try:
            self.camera_monitor = CameraStreamMonitor(self.camera_ip, self.camera_port)
            self.get_logger().info(f'Connected to camera stream at {self.camera_monitor.stream_url}')
        except RuntimeError as exc:
            self.camera_monitor = None
            self.get_logger().error(f'Unable to initialize camera stream: {exc}')

    def cmd_vel_callback(self, msg: Twist) -> None:
        left_speed = int(max(-255, min(255, msg.linear.x * 200 + msg.angular.z * 100)))
        right_speed = int(max(-255, min(255, msg.linear.x * 200 - msg.angular.z * 100)))
        self.send_drive_commands(left_speed, right_speed)

    def send_drive_commands(self, left_speed: int, right_speed: int) -> None:
        self.send_motor_command(1, left_speed)
        self.send_motor_command(2, right_speed)

    def send_motor_command(self, motor_id: int, speed: int) -> None:
        if self._serial is None or not self._serial.is_open:
            self.get_logger().warning('Serial port is not open, cannot send motor command')
            return

        direction = 'F' if speed > 0 else 'B' if speed < 0 else 'S'
        magnitude = abs(int(max(-255, min(255, speed))))
        packet = f'<{motor_id},{direction},{magnitude}>\n'

        with self._lock:
            try:
                self._serial.write(packet.encode('utf-8'))
                self._serial.flush()
                self.get_logger().info(f'Sent motor command: {packet.strip()}')
            except SerialException as exc:
                self.get_logger().error(f'Failed to write serial command: {exc}')

    def _read_loop(self) -> None:
        if self._serial is None:
            return

        while rclpy.ok() and self._running and self._serial.is_open:
            try:
                line = self._serial.readline().decode('utf-8', errors='replace').strip()
                if not line:
                    continue

                if line.startswith('TELEMETRY,'):
                    msg = String()
                    msg.data = line
                    self.telemetry_publisher.publish(msg)
                    self.get_logger().info(f'Published telemetry: {line}')
                else:
                    self.get_logger().debug(f'Unrecognized serial line: {line}')
            except SerialException as exc:
                self.get_logger().error(f'Serial read error: {exc}')
                break
            except Exception as exc:
                self.get_logger().error(f'Unexpected read error: {exc}')

    def _publish_status(self) -> None:
        msg = String()
        if self.camera_monitor is None:
            msg.data = 'camera: unavailable'
        else:
            grabbed, size = self.camera_monitor.get_status()
            msg.data = f'camera: ok {size[0]}x{size[1]}' if grabbed else 'camera: stream opened, no frames yet'

        self.camera_status_publisher.publish(msg)

    def destroy_node(self) -> None:
        self._running = False
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1.0)

        if self._serial and self._serial.is_open:
            try:
                self.send_motor_command(1, 0)
                self.send_motor_command(2, 0)
                self._serial.close()
            except SerialException:
                pass

        if self.camera_monitor:
            self.camera_monitor.stop()

        super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)

    node = SerialRobotController()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('Keyboard interrupt, shutting down')
    finally:
        node.destroy_node()
        rclpy.shutdown()
