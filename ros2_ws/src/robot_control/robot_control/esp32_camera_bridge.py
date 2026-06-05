import re
import threading
import time
import urllib.request
import urllib.error

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from sensor_msgs.msg import Image


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

    def close(self) -> None:
        if self.response is not None:
            try:
                self.response.close()
            except Exception:
                pass
            self.response = None
            self.buffer = b''


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


class CameraStream:
    """Thread-safe camera reader with MJPEG → JPEG fallback.

    All network I/O runs on a background thread so callers never block
    on a slow or unreachable camera.
    """

    def __init__(self, url: str, fallback_failures: int = 3, logger=None):
        self.url = url
        self.reader = None
        self.fallback = None
        self.failure_count = 0
        self.fallback_failures = fallback_failures
        self._logger = logger

        self._lock = threading.Lock()
        self._latest_frame = None
        self._latest_grabbed = False
        self._active = True
        self._thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._thread.start()

    def _log_info(self, msg: str) -> None:
        if self._logger:
            self._logger.info(msg)
        else:
            print(msg)

    def _log_warn(self, msg: str) -> None:
        if self._logger:
            self._logger.warning(msg)
        else:
            print(f'WARN: {msg}')

    def _open_http_reader(self) -> bool:
        try:
            self.reader = MjpegHttpReader(self.url)
            self._log_info(f'MJPEG stream connected: {self.url}')
            return True
        except Exception as exc:
            self.reader = None
            self._log_warn(f'Failed to open MJPEG stream {self.url}: {exc}')
            return False

    def _open_fallback_reader(self):
        if self.fallback is not None:
            return
        try:
            self.fallback = SingleJpgReader(self.url)
            self._log_info(f'Using JPEG snapshot fallback: {self.fallback.url}')
        except Exception as exc:
            self.fallback = None
            self._log_warn(f'Failed to initialize JPEG fallback for {self.url}: {exc}')

    def _reader_loop(self) -> None:
        """Background loop: keep trying to read frames, reconnecting as needed."""
        reconnect_delay = 2.0

        while self._active:
            # Ensure we have at least one reader open
            if self.reader is None and self.fallback is None:
                if not self._open_http_reader():
                    self._open_fallback_reader()
                if self.reader is None and self.fallback is None:
                    time.sleep(reconnect_delay)
                    continue

            grabbed, frame = False, None

            if self.reader is not None:
                try:
                    grabbed, frame = self.reader.read_frame()
                except Exception as exc:
                    self._log_warn(f'MJPEG reader error: {exc}')
                    self.reader.close()
                    self.reader = None

            if not grabbed and self.fallback is None:
                self.failure_count += 1
                if self.failure_count >= self.fallback_failures:
                    self._open_fallback_reader()

            if not grabbed and self.fallback is not None:
                try:
                    grabbed, frame = self.fallback.read_frame()
                except Exception as exc:
                    self._log_warn(f'JPEG fallback error: {exc}')
                    grabbed, frame = False, None

            if grabbed and frame is not None:
                self.failure_count = 0
                with self._lock:
                    self._latest_frame = frame
                    self._latest_grabbed = True
            else:
                self.failure_count += 1
                if self.failure_count >= self.fallback_failures * 2:
                    # Both readers failed repeatedly — tear down and retry
                    if self.reader is not None:
                        self.reader.close()
                        self.reader = None
                    self.fallback = None
                    self.failure_count = 0
                    time.sleep(reconnect_delay)
                else:
                    time.sleep(0.05)

    def read(self):
        """Return the latest frame (thread-safe, non-blocking)."""
        with self._lock:
            if self._latest_grabbed and self._latest_frame is not None:
                frame = self._latest_frame
                self._latest_grabbed = False
                return True, frame
            return False, None

    def release(self):
        self._active = False
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self.reader is not None:
            self.reader.close()
            self.reader = None
        self.fallback = None


class ESP32CameraBridge(Node):
    def __init__(self):
        super().__init__('esp32_camera_bridge')

        self.camera_url = self.declare_parameter('camera_url', 'http://192.168.4.1/stream').value
        self.camera_topic = self.declare_parameter(
            'camera_topic',
            'camera/image_raw',
        ).value
        self.frame_id = self.declare_parameter('frame_id', 'camera').value
        self.publish_rate = float(self.declare_parameter('publish_rate', 10.0).value)

        self.bridge = CvBridge()
        self.publisher = self.create_publisher(Image, self.camera_topic, 1)
        self.stream = CameraStream(self.camera_url, logger=self.get_logger())
        self.timer = self.create_timer(1.0 / self.publish_rate, self._timer_callback)

        self.get_logger().info(f'Starting ESP32 camera bridge to {self.camera_url}')

    def _timer_callback(self):
        grabbed, frame = self.stream.read()
        if not grabbed or frame is None:
            return

        try:
            msg = self.bridge.cv2_to_imgmsg(frame, encoding='bgr8')
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.header.frame_id = self.frame_id
            self.publisher.publish(msg)
            self.get_logger().debug(f'Published image frame {frame.shape[1]}x{frame.shape[0]}')
        except Exception as exc:
            self.get_logger().error(f'Failed to convert/publish camera frame: {exc}')

    def destroy_node(self):
        self.stream.release()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = ESP32CameraBridge()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
