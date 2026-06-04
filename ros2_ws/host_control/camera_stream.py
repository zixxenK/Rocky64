import re
import threading
import time
import urllib.request
import urllib.error

import cv2
import numpy as np


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
        content_type = self.response.getheader('Content-Type', '')
        status = getattr(self.response, 'status', None)
        print(f'Opened MJPEG stream {self.url} status={status} content-type={content_type}')
        if status is not None and status != 200:
            raise ValueError(f'MJPEG stream returned HTTP status {status}')
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
            print(f'Failed to decode MJPEG frame from {self.url}')
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

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass


class AsynchronousCameraStream:
    def __init__(self, ip_address: str, port: int = 80, path: str = "/stream"):
        self.stream_url = f"http://{ip_address}:{port}{path}"
        self.reader = None
        self.fallback = None
        self.grabbed = False
        self.frame = None
        self.active = False
        self.lock = threading.Lock()
        self._failed_reads = 0
        self._reconnect_delay = 1.0
        self._last_reconnect = 0.0

        self._open_reader()

        if not self.reader and not self.fallback:
            raise RuntimeError(
                f"Unable to open camera stream: {self.stream_url}"
            )

        self.active = True
        self.thread = threading.Thread(target=self._update_buffer, daemon=True)
        self.thread.start()

    def _open_reader(self):
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

    def _update_buffer(self):
        while self.active:
            if self.reader is None and self.fallback is None:
                now = time.time()
                if now - self._last_reconnect >= self._reconnect_delay:
                    self._last_reconnect = now
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
                    self._last_reconnect = time.time()
                    if self.reader is not None:
                        self.reader.close()
                        self.reader = None
                    self.fallback = None
                time.sleep(0.05)
                continue

            self._failed_reads = 0
            with self.lock:
                self.grabbed = grabbed
                self.frame = frame

    def read_latest_frame(self):
        with self.lock:
            return self.grabbed, self.frame

    def stop_stream(self):
        self.active = False
        if self.thread.is_alive():
            self.thread.join(timeout=1.0)
        if self.reader is not None:
            self.reader.close()
            self.reader = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop_stream()
