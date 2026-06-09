import argparse
import glob
import importlib
import json
import os
import platform
import socket
import sys
import urllib.error
import urllib.request
from typing import Dict, List, Optional

try:
    import grp
except ImportError:
    grp = None


DEFAULT_AP_CAMERA_IP = '192.168.4.1'
DEFAULT_CAMERA_PORT = 80
DEFAULT_NAMESPACE = 'rock64_1'
DEFAULT_SERIAL_PORT = '/dev/ttyACM0'
DEFAULT_BAUDRATE = 115200
DEFAULT_EXPECTED_SSID = 'TELUS4424'


class Reporter:
    def __init__(self) -> None:
        self.failures = 0
        self.warnings = 0

    def info(self, message: str) -> None:
        print(f'[INFO] {message}')

    def ok(self, message: str) -> None:
        print(f'[ OK ] {message}')

    def warn(self, message: str) -> None:
        self.warnings += 1
        print(f'[WARN] {message}')

    def fail(self, message: str) -> None:
        self.failures += 1
        print(f'[FAIL] {message}')


def is_linux_host() -> bool:
    return platform.system() == 'Linux'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Fresh-start preflight checks for Rock64 ROS2 bringup',
    )
    parser.add_argument(
        '--role',
        choices=['rock64', 'pc'],
        required=True,
        help='Host role to validate',
    )
    parser.add_argument(
        '--network-mode',
        choices=['station', 'ap'],
        default='station',
        help='Expected ESP32 camera network mode',
    )
    parser.add_argument(
        '--camera-ip',
        default=None,
        help='Camera IP address. In AP mode this defaults to 192.168.4.1.',
    )
    parser.add_argument(
        '--camera-port',
        type=int,
        default=DEFAULT_CAMERA_PORT,
        help='Camera HTTP port',
    )
    parser.add_argument(
        '--robot-host',
        default=None,
        help='Rock64 hostname or IP to resolve from the PC',
    )
    parser.add_argument(
        '--serial-port',
        default=DEFAULT_SERIAL_PORT,
        help='Preferred Arduino serial device on the Rock64',
    )
    parser.add_argument(
        '--baudrate',
        type=int,
        default=DEFAULT_BAUDRATE,
        help='Expected Arduino baud rate',
    )
    parser.add_argument(
        '--robot-namespace',
        default=DEFAULT_NAMESPACE,
        help='Expected ROS2 namespace',
    )
    parser.add_argument(
        '--expected-ssid',
        default=DEFAULT_EXPECTED_SSID,
        help='Expected station-mode SSID for the ESP32 camera',
    )
    parser.add_argument(
        '--timeout',
        type=float,
        default=5.0,
        help='Timeout in seconds for network requests',
    )
    parser.add_argument(
        '--skip-stream',
        action='store_true',
        help='Skip the MJPEG stream check',
    )
    return parser.parse_args()


def resolve_camera_ip(args: argparse.Namespace) -> Optional[str]:
    if args.camera_ip:
        return args.camera_ip
    if args.network_mode == 'ap':
        return DEFAULT_AP_CAMERA_IP
    return None


def build_camera_urls(camera_ip: str, camera_port: int) -> Dict[str, str]:
    base = f'http://{camera_ip}:{camera_port}'
    return {
        'status': f'{base}/status',
        'jpg': f'{base}/capture',
        'stream': f'{base}/stream',
    }


def load_optional_module(module_name: str, reporter: Reporter) -> bool:
    try:
        importlib.import_module(module_name)
        reporter.ok(f'Python module available: {module_name}')
        return True
    except Exception as exc:
        reporter.fail(f'Missing Python module {module_name}: {exc}')
        return False


def check_ros_env(reporter: Reporter) -> None:
    domain = os.environ.get('ROS_DOMAIN_ID')
    localhost_only = os.environ.get('ROS_LOCALHOST_ONLY')

    if domain == '0':
        reporter.ok('ROS_DOMAIN_ID is set to 0')
    elif domain is None:
        reporter.warn('ROS_DOMAIN_ID is not set; expected 0 for bringup')
    else:
        reporter.warn(f'ROS_DOMAIN_ID is {domain}; expected 0 for bringup')

    if localhost_only == '0':
        reporter.ok('ROS_LOCALHOST_ONLY is set to 0')
    elif localhost_only is None:
        reporter.warn('ROS_LOCALHOST_ONLY is not set; expected 0 for network discovery')
    else:
        reporter.warn(
            f'ROS_LOCALHOST_ONLY is {localhost_only}; expected 0 for network discovery'
        )


def check_host_resolution(hostname: str, reporter: Reporter) -> None:
    try:
        resolved = socket.gethostbyname(hostname)
        reporter.ok(f'{hostname} resolves to {resolved}')
    except OSError as exc:
        reporter.fail(f'Unable to resolve {hostname}: {exc}')


def check_dialout_membership(reporter: Reporter) -> None:
    if not is_linux_host():
        reporter.info(
            'Non-Linux host detected. Skipping dialout group check.'
        )
        return

    if grp is None:
        reporter.warn('grp module unavailable; skipping dialout group check')
        return

    try:
        dialout_gid = grp.getgrnam('dialout').gr_gid
    except KeyError:
        reporter.warn('dialout group not present on this host')
        return

    if dialout_gid in os.getgroups():
        reporter.ok('Current user has dialout group access')
    else:
        reporter.fail('Current user does not have dialout group access in this session')


def serial_candidates() -> List[str]:
    candidates: List[str] = []
    for pattern in ['/dev/ttyACM*', '/dev/ttyUSB*']:
        candidates.extend(sorted(glob.glob(pattern)))
    return candidates


def check_serial_port(port: str, reporter: Reporter) -> None:
    if not is_linux_host():
        reporter.info(
            'Non-Linux host detected. Skipping /dev/tty serial checks; '
            'rerun on the Rock64 for hardware validation.'
        )
        return

    if os.path.exists(port):
        reporter.ok(f'Serial port exists: {port}')
        return

    candidates = serial_candidates()
    if candidates:
        reporter.warn(
            f'Preferred serial port {port} not found; available candidates: {candidates}'
        )
    else:
        reporter.fail(
            'No Arduino serial candidates found under /dev/ttyACM* or /dev/ttyUSB*'
        )


def request_text(url: str, timeout: float) -> str:
    request = urllib.request.Request(
        url,
        headers={'User-Agent': 'Rock64-Bringup-Preflight/1.0'},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode('utf-8', errors='replace')


def check_status_endpoint(
    camera_urls: Dict[str, str],
    expected_mode: str,
    expected_ssid: str,
    reporter: Reporter,
    timeout: float,
) -> None:
    try:
        payload = json.loads(request_text(camera_urls['status'], timeout))
    except urllib.error.URLError as exc:
        reporter.fail(f'Unable to reach camera status endpoint: {exc.reason}')
        return
    except Exception as exc:
        reporter.fail(f'Unable to read camera status endpoint: {exc}')
        return

    reporter.ok(f"Camera status endpoint reachable: {camera_urls['status']}")
    mode = payload.get('mode') or payload.get('wifi_mode')
    ssid = payload.get('ssid')
    ip_addr = payload.get('ip')
    reporter.info(f'Camera status payload: {json.dumps(payload, indent=2)}')

    if expected_mode == 'station':
        if mode in ('station', 'station_connected'):
            reporter.ok('Camera reports station mode')
        else:
            reporter.warn(f'Camera reports mode={mode}; expected station')
        if ssid == expected_ssid:
            reporter.ok(f'Camera reports expected SSID: {expected_ssid}')
        else:
            reporter.warn(f'Camera reports ssid={ssid}; expected {expected_ssid}')
    else:
        if mode == 'ap':
            reporter.ok('Camera reports AP mode')
        else:
            reporter.warn(f'Camera reports mode={mode}; expected ap')

    if ip_addr:
        reporter.ok(f'Camera reports active IP: {ip_addr}')


def check_jpg_endpoint(
    camera_urls: Dict[str, str],
    reporter: Reporter,
    timeout: float,
) -> None:
    request = urllib.request.Request(
        camera_urls['jpg'],
        headers={'User-Agent': 'Rock64-Bringup-Preflight/1.0'},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = response.getheader('Content-Type', '')
            if 'jpeg' in content_type.lower():
                reporter.ok('Camera JPEG endpoint returned JPEG content')
            else:
                reporter.warn(
                    f'Camera JPEG endpoint returned unexpected content-type: {content_type}'
                )
    except urllib.error.URLError as exc:
        reporter.fail(f'Unable to reach camera JPEG endpoint: {exc.reason}')
    except Exception as exc:
        reporter.fail(f'Unable to validate camera JPEG endpoint: {exc}')


def check_stream_endpoint(
    camera_urls: Dict[str, str],
    reporter: Reporter,
) -> None:
    try:
        cv2 = importlib.import_module('cv2')
    except Exception as exc:
        reporter.fail(f'OpenCV unavailable for stream check: {exc}')
        return

    cap = cv2.VideoCapture(camera_urls['stream'])
    try:
        if not cap.isOpened():
            reporter.fail('Unable to open camera MJPEG stream in OpenCV')
            return
        grabbed, frame = cap.read()
        if not grabbed or frame is None:
            reporter.fail('Camera MJPEG stream opened but no frame was received')
            return
        reporter.ok(
            f'Camera MJPEG stream returned a frame: {frame.shape[1]}x{frame.shape[0]}'
        )
    finally:
        cap.release()


def print_expected_topics(namespace: str, reporter: Reporter) -> None:
    reporter.info('Expected ROS2 topics for this bringup:')
    for topic in [
        f'/{namespace}/cmd_vel',
        f'/{namespace}/camera_servo',
        f'/{namespace}/robot_telemetry',
        f'/{namespace}/camera/image_raw',
    ]:
        reporter.info(f'  {topic}')


def main() -> int:
    args = parse_args()
    reporter = Reporter()
    camera_ip = resolve_camera_ip(args)
    host_os = platform.system()

    reporter.info(f'Role: {args.role}')
    reporter.info(f'Host OS: {host_os}')
    reporter.info(f'Network mode: {args.network_mode}')
    reporter.info(f'Expected station SSID: {args.expected_ssid}')
    reporter.info(f'Expected serial contract: {args.serial_port} @ {args.baudrate}')
    print_expected_topics(args.robot_namespace, reporter)

    if args.role == 'rock64' and not is_linux_host():
        reporter.info(
            'Rock64 role requested on a non-Linux host. Hardware serial '
            'validation will be skipped in this session.'
        )

    reporter.info('Checking Python dependencies...')
    if args.role == 'rock64':
        load_optional_module('serial', reporter)
    if camera_ip is not None:
        load_optional_module('numpy', reporter)
    if camera_ip is not None and not args.skip_stream:
        load_optional_module('cv2', reporter)

    reporter.info('Checking ROS2 environment variables...')
    check_ros_env(reporter)

    if args.role == 'rock64':
        reporter.info('Checking Rock64 serial prerequisites...')
        check_dialout_membership(reporter)
        check_serial_port(args.serial_port, reporter)

    if args.role == 'pc' and args.robot_host:
        reporter.info('Checking Rock64 host resolution from the PC...')
        check_host_resolution(args.robot_host, reporter)

    if camera_ip is None:
        reporter.warn(
            'No camera IP provided for station mode. Discover the DHCP address first or rerun with --camera-ip.'
        )
    else:
        camera_urls = build_camera_urls(camera_ip, args.camera_port)
        reporter.info(f'Camera status URL: {camera_urls["status"]}')
        reporter.info(f'Camera JPEG URL: {camera_urls["jpg"]}')
        reporter.info(f'Camera stream URL: {camera_urls["stream"]}')
        reporter.info('Checking camera status endpoint...')
        check_status_endpoint(
            camera_urls,
            args.network_mode,
            args.expected_ssid,
            reporter,
            args.timeout,
        )
        reporter.info('Checking camera JPEG endpoint...')
        check_jpg_endpoint(camera_urls, reporter, args.timeout)
        if not args.skip_stream:
            reporter.info('Checking camera MJPEG stream...')
            check_stream_endpoint(camera_urls, reporter)

    if reporter.failures:
        reporter.fail(
            f'Preflight completed with {reporter.failures} failure(s) and {reporter.warnings} warning(s).'
        )
        return 1

    if reporter.warnings:
        reporter.warn(
            f'Preflight completed with warnings only ({reporter.warnings}).'
        )
    else:
        reporter.ok('Preflight completed without failures or warnings.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print('Interrupted by user.')
        sys.exit(1)