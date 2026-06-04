import argparse
import json
import sys
import time
import urllib.error
import urllib.request

import cv2


def test_jpg(url: str, timeout: float) -> None:
    print(f"Testing single-frame endpoint: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "ESP32-CAM-Diagnostics/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = response.getheader("Content-Type")
            length = response.getheader("Content-Length")
            print(f"  HTTP {response.status} {response.reason}")
            print(f"  Content-Type: {content_type}")
            print(f"  Content-Length: {length}")
            data = response.read(64)
            print(f"  Received {len(data)} bytes (preview)")
            if content_type and "jpeg" in content_type.lower():
                print("  Single-frame endpoint returned JPEG data.")
            else:
                print("  Warning: unexpected content type for JPEG endpoint.")
    except urllib.error.HTTPError as exc:
        print(f"  HTTP error: {exc.code} {exc.reason}")
    except urllib.error.URLError as exc:
        print(f"  URL error: {exc.reason}")
    except Exception as exc:
        print(f"  Unexpected error: {exc}")


def test_status(url: str, timeout: float) -> None:
    print(f"Testing status endpoint: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "ESP32-CAM-Diagnostics/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            print(f"  HTTP {response.status} {response.reason}")
            content_type = response.getheader("Content-Type")
            print(f"  Content-Type: {content_type}")
            body = response.read(512).decode("utf-8", errors="replace")
            try:
                payload = json.loads(body)
                print(f"  Response JSON: {json.dumps(payload, indent=2)}")
            except ValueError:
                print(f"  Unexpected response body: {body}")
    except urllib.error.HTTPError as exc:
        print(f"  HTTP error: {exc.code} {exc.reason}")
    except urllib.error.URLError as exc:
        print(f"  URL error: {exc.reason}")
    except Exception as exc:
        print(f"  Unexpected error: {exc}")


def test_stream(url: str, timeout: float, frames_to_check: int = 5) -> None:
    print(f"Testing MJPEG stream: {url}")
    cap = cv2.VideoCapture(url)
    if not cap.isOpened():
        print("  Failed to open OpenCV stream.")
        return

    start = time.time()
    frames = 0
    while frames < frames_to_check and time.time() - start < timeout:
        grabbed, frame = cap.read()
        if not grabbed:
            print("  No frame yet, retrying...")
            time.sleep(0.2)
            continue
        frames += 1
        height, width = frame.shape[:2]
        print(f"  Frame {frames}: {width}x{height}")

    cap.release()
    if frames >= frames_to_check:
        print(f"  Successfully received {frames} frames.")
    else:
        print(f"  Only received {frames} frames in {timeout}s.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ESP32-CAM stream diagnostic helper for PC troubleshooting"
    )
    parser.add_argument(
        "--camera-ip",
        default="192.168.4.1",
        help="ESP32 camera IP address",
    )
    parser.add_argument(
        "--camera-port",
        type=int,
        default=80,
        help="ESP32 camera HTTP port",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Timeout in seconds for each test",
    )
    parser.add_argument(
        "--no-status",
        action="store_true",
        help="Skip the /status endpoint test",
    )
    parser.add_argument(
        "--no-jpg",
        action="store_true",
        help="Skip single-frame JPEG endpoint test",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="Skip MJPEG stream test",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    jpg_url = f"http://{args.camera_ip}:{args.camera_port}/jpg"
    stream_url = f"http://{args.camera_ip}:{args.camera_port}/stream"

    print("ESP32-CAM PC Stream Diagnostics")
    status_url = f"http://{args.camera_ip}:{args.camera_port}/status"
    print(f"Camera URL: {stream_url}")
    print(f"Single-frame URL: {jpg_url}")
    print(f"Status URL: {status_url}")
    print("---")

    if not args.no_status:
        test_status(status_url, args.timeout)
        print("---")

    if not args.no_jpg:
        test_jpg(jpg_url, args.timeout)
        print("---")

    if not args.no_stream:
        test_stream(stream_url, args.timeout)
        print("---")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted by user.")
        sys.exit(1)
