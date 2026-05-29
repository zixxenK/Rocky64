import argparse
import time
from host_control.serial_bridge import TelemetrySerialBridge
from host_control.camera_stream import AsynchronousCameraStream


def build_argument_parser():
    parser = argparse.ArgumentParser(
        description="Rock64 Robot host control and camera integration"
    )
    parser.add_argument(
        "--serial-port",
        default="/dev/ttyS1",
        help="Serial port for Arduino Uno connection",
    )
    parser.add_argument(
        "--baudrate",
        type=int,
        default=115200,
        help="Baud rate for serial communication",
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
    return parser


def main():
    parser = build_argument_parser()
    args = parser.parse_args()

    print("Starting Rock64 host controller")
    print(f"Serial port: {args.serial_port} @ {args.baudrate}")
    print(f"Camera stream: http://{args.camera_ip}:{args.camera_port}/stream")

    try:
        with TelemetrySerialBridge(
            port=args.serial_port,
            baudrate=args.baudrate,
        ) as bridge:
            with AsynchronousCameraStream(
                ip_address=args.camera_ip,
                port=args.camera_port,
            ) as camera:
                print("Connected to serial bridge and camera stream.")

                for _ in range(10):
                    bridge.send_motor_command(1, "F", 64)
                    bridge.send_motor_command(2, "F", 64)
                    time.sleep(0.2)
                    bridge.send_motor_command(1, "S", 0)
                    bridge.send_motor_command(2, "S", 0)
                    time.sleep(0.2)

                    grabbed, frame = camera.read_latest_frame()
                    if grabbed:
                        width = frame.shape[1]
                        height = frame.shape[0]
                        print(f"Frame received: {width}x{height}")
                    else:
                        print("No frame received yet.")

                print("Stopping motors and exiting.")
                bridge.send_emergency_stop()
    except RuntimeError as exc:
        print(f"Fatal error: {exc}")
    except KeyboardInterrupt:
        print("Interrupted by user.")


if __name__ == "__main__":
    main()
