import glob
import os
import re
import threading
import time
import urllib.request
import urllib.error
from typing import Optional, Tuple

import cv2
import numpy as np
import rclpy
import serial
from geometry_msgs.msg import Twist
from rclpy.node import Node
from serial import SerialException
from std_msgs.msg import String


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


class MjpegHttpReader:
    def __init__(self, url: str, timeout: float = 10.0, reconnect_delay: float = 2.0):
        self.url = url
        self.timeout = timeout
        self.reconnect_delay = reconnect_delay
        self.boundary = b'--frame'
        self.response = None
        self.buffer = b''
        self.last_open = 0.0
        self._open_stream()

    def _parse_boundary(self, content_type: str) -> None:
        match = re.search(r'boundary="?([^";]+)"?', content_type or '')
        if match:
            self.boundary = b'--' + match.group(1).encode('utf-8')

    def _open_stream(self) -> None:
        if self.response is not None:
            try:
                self.response.close()
            except Exception:
                pass

        req = urllib.request.Request(self.url, headers={'User-Agent': 'Mozilla/5.0'})
        self.response = urllib.request.urlopen(req, timeout=self.timeout)
        self._parse_boundary(self.response.getheader('Content-Type', ''))
        self.buffer = b''
        self.last_open = time.time()

    def read_frame(self):
        if self.response is None:
            if time.time() - self.last_open < self.reconnect_delay:
                time.sleep(self.reconnect_delay)
            self._open_stream()

        while True:
            boundary_index = self.buffer.find(self.boundary)
            if boundary_index != -1:
                self.buffer = self.buffer[boundary_index + len(self.boundary):]
                break

            chunk = self.response.read(4096)
            if not chunk:
                self._reconnect()
                return False, None
            self.buffer += chunk

        if self.buffer.startswith(b'\r\n'):
            self.buffer = self.buffer[2:]

        header_end = self.buffer.find(b'\r\n\r\n')
        while header_end == -1:
            chunk = self.response.read(4096)
            if not chunk:
                self._reconnect()
                return False, None
            self.buffer += chunk
            header_end = self.buffer.find(b'\r\n\r\n')

        header_bytes = self.buffer[:header_end]
        self.buffer = self.buffer[header_end + 4:]

        headers = {}
        for line in header_bytes.split(b'\r\n'):
            parts = line.split(b':', 1)
            if len(parts) == 2:
                headers[parts[0].strip().lower()] = parts[1].strip()

        length = int(headers.get(b'content-length', b'0'))
        if length <= 0:
            self._reconnect()
            return False, None

        while len(self.buffer) < length:
            chunk = self.response.read(length - len(self.buffer))
            if not chunk:
                self._reconnect()
                return False, None
            self.buffer += chunk

        frame_bytes = self.buffer[:length]
        self.buffer = self.buffer[length:]

        frame = cv2.imdecode(np.frombuffer(frame_bytes, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return False, None

        return True, frame

    def _reconnect(self) -> None:
        if self.response is not None:
            try:
                self.response.close()
            except Exception:
                pass
        self.response = None
        self.buffer = b''
        self.last_open = time.time()


class SingleJpgReader:
    def __init__(self, url: str, timeout: float = 10.0):
        self.timeout = timeout
        self.url = self._build_jpg_url(url)

    def _build_jpg_url(self, url: str) -> str:
        if url.endswith('/jpg'):
            return url
        if url.endswith('/stream'):
            return url[:-len('/stream')] + '/jpg'
        return url.rstrip('/') + '/jpg'

    def read_frame(self):
        req = urllib.request.Request(self.url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            status = getattr(response, 'status', None)
            if status is not None and status != 200:
                raise ValueError(f'JPEG request returned status {status}')
            frame_bytes = response.read()

        frame = cv2.imdecode(np.frombuffer(frame_bytes, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError(f'Failed to decode JPEG from {self.url}')

        return True, frame

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass


class CameraStreamMonitor:
    def __init__(self, ip_address: str, port: int = 80, path: str = '/stream'):
        self.stream_url = f'http://{ip_address}:{port}{path}'
        self.reader = None
        self.fallback = None
        self.grabbed = False
        self.frame_size = (0, 0)
        self.active = False
        self.lock = threading.Lock()
        self.thread: Optional[threading.Thread] = None
        self._failed_reads = 0

        self._open_reader()
        if self.reader is None and self.fallback is None:
            raise RuntimeError(f'Unable to open camera stream: {self.stream_url}')

        self.active = True
        self.thread = threading.Thread(target=self._update_buffer, daemon=True)
        self.thread.start()

    def _open_reader(self) -> None:
        try:
            self.reader = MjpegHttpReader(self.stream_url)
        except Exception:
            self.reader = None

        if self.reader is None and self.fallback is None:
            try:
                self.fallback = SingleJpgReader(self.stream_url)
                print(f'Using JPEG snapshot fallback for camera URL: {self.fallback.url}')
            except Exception:
                self.fallback = None

    def _update_buffer(self) -> None:
        while self.active:
            if self.reader is None and self.fallback is None:
                self._open_reader()
                time.sleep(0.1)
                continue

            if self.reader is not None:
                grabbed, frame = self.reader.read_frame()
            elif self.fallback is not None:
                try:
                    grabbed, frame = self.fallback.read_frame()
                except Exception as exc:
                    print(f'JPEG fallback error: {exc}')
                    grabbed, frame = False, None
            else:
                grabbed, frame = False, None

            if not grabbed or frame is None:
                self._failed_reads += 1
                if self._failed_reads >= 5:
                    self._failed_reads = 0
                    if self.reader is not None:
                        self.reader.close()
                        self.reader = None
                    self.fallback = None
                time.sleep(0.05)
                continue

            self._failed_reads = 0
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
        if self.reader is not None:
            self.reader.close()
            self.reader = None
        self.fallback = None


class SerialRobotController(Node):
    def __init__(
        self,
        port: str = '/dev/ttyUSB0',
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
        self.port = _select_serial_port(self.port)
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
        self.send_motor_command(1, right_speed)  # Motor 1 = Right
        self.send_motor_command(2, left_speed)   # Motor 2 = Left

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
