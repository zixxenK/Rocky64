"""arduino_serial_bridge.py  —  Production-grade ROS 2 ↔ Arduino serial node.

Architecture
------------
  _declare_parameters()      : All tunables read from the ROS 2 param server / YAML.
  _discover_port()           : VID/PID scan → glob fallback → configured port param.
  _connect()                 : Opens serial, resets input buffer; non-fatal on failure.
  _start_writer_thread()     : Daemon thread drains _write_queue; callbacks never block.
  _create_subscriptions()    : Relative topic names → namespace applied by launch file.
  _start_reconnect_timer()   : Polls _connect() every retry_delay s when disconnected.
  _start_watchdog_timer()    : Logs WARN once when cmd_vel goes stale > watchdog_timeout_ms.

Safety contract
---------------
  The Arduino firmware owns motor safety via its 200 ms checkHeartbeat() watchdog.
  This node NEVER sends autonomous stop commands — it only logs stale-cmd warnings.
  Sending duplicate stops would create two independent safety owners and mask firmware
  failures (e.g. firmware crashed but node thinks it sent STOP → false confidence).
"""
import glob as _glob
import queue
import threading
import time
from typing import Optional

import serial
import serial.tools.list_ports
from serial import SerialException

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import Int16, String

from robot_control.control_mapping import twist_to_wheel_speeds, motor_packet


# ---------------------------------------------------------------------------
# Module-level helpers (no ROS dependencies — independently testable)
# ---------------------------------------------------------------------------

def find_arduino_port(vid: int, pid: int) -> Optional[str]:
    """Scan attached serial ports and return the first one matching VID.

    If *pid* is not -1 the PID must also match (use -1 to accept any PID for
    the given VID, which is safe when only one Arduino family is ever attached).
    """
    for info in serial.tools.list_ports.comports():
        if info.vid == vid:
            if pid == -1 or info.pid == pid:
                return info.device
    return None


def glob_fallback_port() -> Optional[str]:
    """Return the lowest-numbered /dev/ttyACM* or /dev/ttyUSB* device found."""
    for pattern in ('/dev/ttyACM*', '/dev/ttyUSB*'):
        matches = sorted(_glob.glob(pattern))
        if matches:
            return matches[0]
    return None


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

class ArduinoSerialBridge(Node):
    """ROS 2 node that bridges cmd_vel / camera_servo topics to Arduino serial."""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(self) -> None:
        super().__init__('arduino_serial_bridge')
        self._declare_parameters()

        # Serial state
        self._ser: Optional[serial.Serial] = None
        self._connected: bool = False
        self._disconnect_logged: bool = False  # rate-limiter for disconnect warnings

        # Writer thread state
        self._write_queue: queue.Queue = queue.Queue(maxsize=32)
        self._shutdown: bool = False

        # Watchdog state
        self._watchdog_fired: bool = False
        self._last_cmd_time: float = time.monotonic()

        # Reader thread state
        self._reader_thread: Optional[threading.Thread] = None

        # Bring up in dependency order
        self._connect()
        self._start_writer_thread()
        self._start_reader_thread()
        self._create_subscriptions()
        self._start_reconnect_timer()
        self._start_watchdog_timer()

    # ------------------------------------------------------------------
    # Parameter declaration
    # ------------------------------------------------------------------

    def _declare_parameters(self) -> None:
        self.declare_parameter('serial_port', '/dev/ttyUSB0')
        self.declare_parameter('baud_rate', 115200)
        self.declare_parameter('timeout', 0.1)
        self.declare_parameter('retry_delay', 5.0)
        # VID 0x2341 = Arduino LLC; set arduino_pid in YAML for board-specific matching
        self.declare_parameter('arduino_vid', 0x2341)
        self.declare_parameter('arduino_pid', -1)       # -1 = any PID for that VID
        # ROS-side stale-cmd monitor (firmware handles the actual cutoff at 200 ms)
        self.declare_parameter('watchdog_timeout_ms', 500.0)
        # Relative topic names — namespace applied by the launch file
        self.declare_parameter('cmd_vel_topic', 'cmd_vel')
        self.declare_parameter('camera_servo_topic', 'camera_servo')
        self.declare_parameter('telemetry_topic', 'robot_telemetry')
        self.declare_parameter('ultrasonic_distance_topic', 'ultrasonic_distance')

    # ------------------------------------------------------------------
    # Port discovery
    # ------------------------------------------------------------------

    def _discover_port(self) -> str:
        """Resolve the serial port using three strategies, in priority order:

        1. VID/PID scan   — hardware-identity match, survives port index changes.
        2. Glob fallback  — first /dev/ttyACM* or /dev/ttyUSB* found.
        3. Configured     — ``serial_port`` param as last resort.
        """
        vid: int = self.get_parameter('arduino_vid').value
        pid: int = self.get_parameter('arduino_pid').value

        port = find_arduino_port(vid, pid)
        if port:
            pid_str = 'any' if pid == -1 else f'0x{pid:04X}'
            self.get_logger().info(
                f'[Discovery] VID/PID match: VID=0x{vid:04X} PID={pid_str} → {port}'
            )
            return port

        port = glob_fallback_port()
        if port:
            self.get_logger().warn(
                f'[Discovery] VID/PID scan found nothing; glob fallback → {port}'
            )
            return port

        port = self.get_parameter('serial_port').value
        self.get_logger().warn(
            f'[Discovery] No device found by scan or glob; using configured port: {port}'
        )
        return port

    # ------------------------------------------------------------------
    # Serial connection management
    # ------------------------------------------------------------------

    def _connect(self) -> bool:
        """Attempt to open the serial port.  Non-fatal — reconnect timer will retry."""
        if self._connected:
            return True

        baud: int = self.get_parameter('baud_rate').value
        timeout: float = self.get_parameter('timeout').value
        port: str = self._discover_port()

        try:
            self._ser = serial.Serial(port, baud, timeout=timeout)
            self._ser.reset_input_buffer()   # discard stale bytes from previous session
            self._connected = True
            self._disconnect_logged = False
            self.get_logger().info(f'Connected to Arduino: {port} @ {baud} baud')
            return True
        except SerialException as exc:
            self.get_logger().error(f'Serial open failed ({port}): {exc}')
            self.get_logger().error(
                'Hint: verify cable and run  sudo usermod -a -G dialout $USER  then re-login.'
            )
            self._ser = None
            self._connected = False
            return False

    def _handle_disconnect(self) -> None:
        """Mark node as disconnected and drain the write queue.

        Called from the writer thread on a SerialException.  Draining the queue
        prevents stale commands from being replayed when the cable is reinserted.
        """
        if self._connected:
            retry: float = self.get_parameter('retry_delay').value
            self.get_logger().warn(
                f'Arduino disconnected. Clearing command queue. '
                f'Reconnect attempt every {retry:.1f} s.'
            )
        self._connected = False
        # Drain stale commands
        while not self._write_queue.empty():
            try:
                self._write_queue.get_nowait()
            except queue.Empty:
                break

    # ------------------------------------------------------------------
    # Non-blocking writer thread
    # ------------------------------------------------------------------

    def _start_writer_thread(self) -> None:
        self._writer_thread = threading.Thread(
            target=self._write_worker, daemon=True, name='arduino_writer'
        )
        self._writer_thread.start()

    def _write_worker(self) -> None:
        """Background thread: drain _write_queue and forward packets to serial.

        Blocking here keeps the ROS 2 spin thread free for subscription callbacks
        and timer callbacks.  The 1-second get() timeout allows clean shutdown.
        """
        while not self._shutdown:
            try:
                packet: bytes = self._write_queue.get(timeout=1.0)
            except queue.Empty:
                continue   # timeout → re-check _shutdown flag

            if not self._connected or self._ser is None:
                continue   # drop packet; reconnect timer will restore the link

            try:
                self._ser.write(packet)
                # pyserial auto-flushes; no explicit flush() needed here
            except SerialException:
                self._handle_disconnect()

    def _send_to_arduino(self, packet: str) -> None:
        """Enqueue a packet for async serial transmission.

        Never blocks the calling ROS 2 callback thread.  Drops packets silently
        when disconnected (after logging once) or when the 32-packet queue is full.
        """
        if not self._connected:
            if not self._disconnect_logged:
                self.get_logger().warn('Cannot send: Arduino not connected.')
                self._disconnect_logged = True
            return
        try:
            self._write_queue.put_nowait(packet.encode('utf-8'))
        except queue.Full:
            self.get_logger().warn('Write queue full — packet dropped.')

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    def _create_subscriptions(self) -> None:
        cmd_vel_topic: str = self.get_parameter('cmd_vel_topic').value
        servo_topic: str = self.get_parameter('camera_servo_topic').value
        ultrasonic_topic: str = self.get_parameter('ultrasonic_distance_topic').value

        self.create_subscription(Twist, cmd_vel_topic, self.cmd_vel_callback, 10)
        self.create_subscription(Int16, servo_topic, self.servo_callback, 10)

        # Create publisher for ultrasonic distance data
        self.ultrasonic_pub = self.create_publisher(Int16, ultrasonic_topic, 10)

        self.get_logger().info(
            f'Subscribed:  {cmd_vel_topic},  {servo_topic}  '
            f'(namespace: {self.get_namespace()})'
        )
        self.get_logger().info(f'Publishing ultrasonic distance to: {ultrasonic_topic}')

    def cmd_vel_callback(self, msg: Twist) -> None:
        self._last_cmd_time = time.monotonic()
        self._watchdog_fired = False   # reset stale flag on any new command

        left_speed, right_speed = twist_to_wheel_speeds(msg.linear.x, msg.angular.z)
        # Motor 1 = Right wheel, Motor 2 = Left wheel (matches firmware pinout)
        self._send_to_arduino(motor_packet(1, right_speed))
        self._send_to_arduino(motor_packet(2, left_speed))

    def servo_callback(self, msg: Int16) -> None:
        position = max(0, min(180, msg.data))
        self._send_to_arduino(f'<SERVO,{position}>\n')

    # ------------------------------------------------------------------
    # Reader thread
    # ------------------------------------------------------------------

    def _start_reader_thread(self) -> None:
        self._reader_thread = threading.Thread(
            target=self._read_worker, daemon=True, name='arduino_reader'
        )
        self._reader_thread.start()

    def _read_worker(self) -> None:
        """Background thread: read serial data from Arduino and parse telemetry."""
        while not self._shutdown:
            if not self._connected or self._ser is None:
                time.sleep(0.1)
                continue

            try:
                if self._ser.in_waiting > 0:
                    line = self._ser.readline().decode('utf-8', errors='replace').strip()
                    if line:
                        self._parse_telemetry(line)
            except SerialException:
                self._handle_disconnect()
                break
            except Exception as exc:
                self.get_logger().error(f'Read error: {exc}')
                time.sleep(0.1)

    def _parse_telemetry(self, line: str) -> None:
        """Parse telemetry packets from Arduino."""
        if line.startswith('<DISTANCE,'):
            try:
                # Parse <DISTANCE,cm>
                parts = line[len('<DISTANCE,'):-1].split(',')
                if len(parts) == 1:
                    distance = int(parts[0])
                    msg = Int16(data=distance)
                    self.ultrasonic_pub.publish(msg)
                    self.get_logger().debug(f'Ultrasonic distance: {distance} cm')
            except (ValueError, IndexError) as exc:
                self.get_logger().warn(f'Failed to parse DISTANCE packet: {line} - {exc}')
        elif line.startswith('<ALERT,OBSTACLE,'):
            try:
                # Parse <ALERT,OBSTACLE,cm>
                parts = line[len('<ALERT,OBSTACLE,'):-1].split(',')
                if len(parts) == 1:
                    distance = int(parts[0])
                    self.get_logger().warn(f'OBSTACLE ALERT: {distance} cm - Emergency stop triggered')
            except (ValueError, IndexError) as exc:
                self.get_logger().warn(f'Failed to parse ALERT packet: {line} - {exc}')
        elif line.startswith('TELEMETRY,'):
            # Forward existing telemetry
            msg = String()
            msg.data = line
            # Note: telemetry_publisher is not currently defined in this node
            # This would need to be added if you want to forward TELEMETRY packets
            self.get_logger().debug(f'Telemetry: {line}')

    # ------------------------------------------------------------------
    # Reconnect timer
    # ------------------------------------------------------------------

    def _start_reconnect_timer(self) -> None:
        retry_delay: float = self.get_parameter('retry_delay').value
        self._reconnect_timer = self.create_timer(retry_delay, self._reconnect_cb)

    def _reconnect_cb(self) -> None:
        if not self._connected:
            self._connect()

    # ------------------------------------------------------------------
    # Watchdog timer  (logging only — firmware owns the motor cutoff)
    # ------------------------------------------------------------------

    def _start_watchdog_timer(self) -> None:
        # Poll at 200 ms to detect stalls promptly relative to the 500 ms threshold
        self._watchdog_timer = self.create_timer(0.2, self._watchdog_cb)

    def _watchdog_cb(self) -> None:
        timeout_s: float = self.get_parameter('watchdog_timeout_ms').value / 1000.0
        stale: bool = (time.monotonic() - self._last_cmd_time) > timeout_s

        if stale and not self._watchdog_fired:
            threshold_ms = self.get_parameter('watchdog_timeout_ms').value
            self.get_logger().warn(
                f'cmd_vel stale for >{threshold_ms:.0f} ms. '
                f'Arduino firmware cuts motors at its own 200 ms timeout.'
            )
            self._watchdog_fired = True

    # ------------------------------------------------------------------
    # Clean shutdown
    # ------------------------------------------------------------------

    def destroy_node(self) -> None:
        self._shutdown = True

        # Send STOP directly — bypass the queue since we may be draining it
        if self._connected and self._ser is not None:
            try:
                self._ser.write(b'<1,S,0>\n<2,S,0>\n')
            except SerialException:
                pass

        if hasattr(self, '_writer_thread'):
            self._writer_thread.join(timeout=2.0)

        if self._ser is not None and self._ser.is_open:
            self._ser.close()
            self.get_logger().info('Serial port closed.')

        super().destroy_node()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(args=None) -> None:
    rclpy.init(args=args)
    node = ArduinoSerialBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()