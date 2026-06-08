#!/usr/bin/env python3
"""lan_camera_restream.py - fan the ESP32 camera out to the whole LAN.

The ESP32-CAM is a tiny device: every extra MJPEG client it serves costs it
bandwidth and frame rate, and a flaky WiFi client can stall its stream. This
script runs **on the Rock64**, opens a **single** upstream connection to the
ESP32 stream, and re-serves those frames to as many local-network viewers as
you like (laptops, phones, tablets) over plain HTTP.

    ESP32-CAM  --one MJPEG connection-->  Rock64 (this script)  --fan-out-->  many viewers

It is pure standard library (no OpenCV, no Flask): frames are relayed as raw
JPEG bytes, so it is light enough to run alongside the ROS 2 bringup.

Endpoints (default port 8080):
    /              minimal HTML page that displays the live stream
    /stream        MJPEG (multipart/x-mixed-replace) - point any browser here
    /snapshot.jpg  the latest single JPEG frame
    /status        JSON health (upstream URL, connected, frames, clients)

Usage (on the Rock64):
    python3 lan_camera_restream.py --camera-ip 192.168.1.153
    python3 lan_camera_restream.py --upstream http://esp32-cam.local/stream --port 8080

Then on any device on the same WiFi:  http://<rock64-ip>:8080/
"""

import argparse
import json
import re
import socket
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BOUNDARY = 'frame'


class FrameHub:
    """Holds the latest JPEG frame and notifies waiting client threads."""

    def __init__(self):
        self._lock = threading.Condition()
        self._frame = None
        self._seq = 0
        self.connected = False
        self.frames_total = 0
        self.last_frame_time = 0.0

    def publish(self, jpeg: bytes) -> None:
        with self._lock:
            self._frame = jpeg
            self._seq += 1
            self.frames_total += 1
            self.last_frame_time = time.time()
            self._lock.notify_all()

    def latest(self):
        with self._lock:
            return self._frame, self._seq

    def wait_for(self, last_seq: int, timeout: float):
        """Block until a frame newer than ``last_seq`` exists (or timeout)."""
        with self._lock:
            if self._seq == last_seq:
                self._lock.wait(timeout)
            return self._frame, self._seq


class UpstreamGrabber(threading.Thread):
    """Single connection to the ESP32 MJPEG stream; relays raw JPEG frames."""

    def __init__(self, url: str, hub: FrameHub, timeout: float = 10.0,
                 reconnect_delay: float = 2.0):
        super().__init__(daemon=True)
        self.url = url
        self.hub = hub
        self.timeout = timeout
        self.reconnect_delay = reconnect_delay
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                self._read_stream()
            except Exception as exc:  # noqa: BLE001 - resilience over precision
                self.hub.connected = False
                print(f"[restream] upstream error: {exc}; reconnecting in "
                      f"{self.reconnect_delay}s")
                self._stop.wait(self.reconnect_delay)

    @staticmethod
    def _read_some(resp, n: int) -> bytes:
        """Read up to ``n`` bytes, returning as soon as *any* data arrives.

        ``HTTPResponse.read(n)`` blocks until the full ``n`` bytes are
        buffered, which batches many frames together and adds latency on a
        live stream. ``read1`` returns whatever a single underlying read
        yields, so frames are relayed as they arrive.
        """
        read1 = getattr(resp, 'read1', None)
        return read1(n) if read1 is not None else resp.read(n)

    def _read_stream(self) -> None:
        req = urllib.request.Request(self.url, headers={'User-Agent': 'Rock64-restream'})
        resp = urllib.request.urlopen(req, timeout=self.timeout)
        boundary = self._parse_boundary(resp.getheader('Content-Type', ''))
        self.hub.connected = True
        print(f"[restream] connected upstream {self.url} (boundary={boundary!r})")

        buf = b''
        while not self._stop.is_set():
            # Find the part boundary.
            idx = buf.find(boundary)
            while idx == -1:
                chunk = self._read_some(resp, 4096)
                if not chunk:
                    raise ConnectionError("upstream closed")
                buf += chunk
                idx = buf.find(boundary)
            buf = buf[idx + len(boundary):]

            # Read past the part headers to the blank line.
            hdr_end = buf.find(b'\r\n\r\n')
            while hdr_end == -1:
                chunk = self._read_some(resp, 4096)
                if not chunk:
                    raise ConnectionError("upstream closed")
                buf += chunk
                hdr_end = buf.find(b'\r\n\r\n')
            header_bytes = buf[:hdr_end]
            buf = buf[hdr_end + 4:]

            length = self._content_length(header_bytes)
            if length <= 0:
                # No length given: fall back to scanning for the next boundary.
                continue

            while len(buf) < length:
                chunk = self._read_some(resp, length - len(buf))
                if not chunk:
                    raise ConnectionError("upstream closed")
                buf += chunk

            jpeg = buf[:length]
            buf = buf[length:]
            self.hub.publish(jpeg)

    @staticmethod
    def _parse_boundary(content_type: str) -> bytes:
        match = re.search(r'boundary="?([^";]+)"?', content_type or '')
        token = match.group(1) if match else 'frame'
        return b'--' + token.encode('utf-8')

    @staticmethod
    def _content_length(header_bytes: bytes) -> int:
        for line in header_bytes.split(b'\r\n'):
            parts = line.split(b':', 1)
            if len(parts) == 2 and parts[0].strip().lower() == b'content-length':
                try:
                    return int(parts[1].strip())
                except ValueError:
                    return 0
        return 0


INDEX_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Rock64 camera</title>
<style>body{{margin:0;background:#111;color:#eee;font-family:sans-serif;
text-align:center}}img{{max-width:100%;height:auto}}</style></head>
<body><h3>Rock64 camera (re-streamed from ESP32)</h3>
<img src="/stream" alt="camera stream"></body></html>"""


def make_handler(hub: FrameHub, upstream_url: str):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *args):  # quiet default per-request logging
            pass

        def do_GET(self):  # noqa: N802 - http.server API
            if self.path.startswith('/stream'):
                self._serve_stream()
            elif self.path.startswith('/snapshot'):
                self._serve_snapshot()
            elif self.path.startswith('/status'):
                self._serve_status()
            elif self.path in ('/', '/index.html'):
                self._serve_index()
            else:
                self.send_error(404, "Not found")

        def _serve_index(self):
            body = INDEX_HTML.format().encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve_snapshot(self):
            frame, _ = hub.latest()
            if frame is None:
                self.send_error(503, "No frame yet")
                return
            self.send_response(200)
            self.send_header('Content-Type', 'image/jpeg')
            self.send_header('Content-Length', str(len(frame)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(frame)

        def _serve_status(self):
            payload = json.dumps({
                'upstream': upstream_url,
                'connected': hub.connected,
                'frames_total': hub.frames_total,
                'last_frame_age_s': round(time.time() - hub.last_frame_time, 2)
                if hub.last_frame_time else None,
            }).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _serve_stream(self):
            self.send_response(200)
            self.send_header(
                'Content-Type',
                f'multipart/x-mixed-replace; boundary={BOUNDARY}',
            )
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Connection', 'close')
            self.end_headers()
            last_seq = -1
            try:
                while True:
                    frame, last_seq = hub.wait_for(last_seq, timeout=5.0)
                    if frame is None:
                        continue
                    chunk = (
                        f'--{BOUNDARY}\r\n'
                        f'Content-Type: image/jpeg\r\n'
                        f'Content-Length: {len(frame)}\r\n\r\n'
                    ).encode('utf-8') + frame + b'\r\n'
                    self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass  # viewer disconnected - normal

    return Handler


def build_upstream_url(args) -> str:
    if args.upstream:
        return args.upstream
    port = '' if str(args.camera_port) == '80' else f':{args.camera_port}'
    return f'http://{args.camera_ip}{port}/stream'


def local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '0.0.0.0'


def main():
    parser = argparse.ArgumentParser(
        description="Re-stream the ESP32 camera to the whole LAN from the Rock64."
    )
    parser.add_argument('--camera-ip', default='192.168.1.153',
                        help='ESP32 camera IP / hostname')
    parser.add_argument('--camera-port', default='80')
    parser.add_argument('--upstream', default='',
                        help='Full upstream MJPEG URL (overrides --camera-ip/--camera-port)')
    parser.add_argument('--host', default='0.0.0.0',
                        help='Address to bind the re-stream server to')
    parser.add_argument('--port', type=int, default=8080,
                        help='Port to serve the re-stream on (default 8080)')
    args = parser.parse_args()

    upstream = build_upstream_url(args)
    hub = FrameHub()
    grabber = UpstreamGrabber(upstream, hub)
    grabber.start()

    server = ThreadingHTTPServer((args.host, args.port), make_handler(hub, upstream))
    server.daemon_threads = True
    shown_host = local_ip() if args.host in ('0.0.0.0', '') else args.host
    print(f"[restream] upstream : {upstream}")
    print(f"[restream] serving  : http://{shown_host}:{args.port}/  "
          f"(/stream /snapshot.jpg /status)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        grabber.stop()
        server.shutdown()
        print("[restream] stopped.")


if __name__ == '__main__':
    main()
