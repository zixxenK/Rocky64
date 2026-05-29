#!/usr/bin/env python3

import threading

import rospy
import serial
from geometry_msgs.msg import Twist
from std_msgs.msg import String


class ArduinoSerialBridge(object):
    def __init__(self):
        self.port = rospy.get_param('~serial_port', '/dev/ttyS1')
        self.baudrate = rospy.get_param('~baudrate', 115200)
        self.timeout = rospy.get_param('~timeout', 0.1)
        self.cmd_vel_topic = rospy.get_param('~cmd_vel_topic', '/cmd_vel')
        self.telemetry_topic = rospy.get_param('~telemetry_topic', '/robot_telemetry')
        self.reconnect_delay = rospy.get_param('~reconnect_delay', 5.0)

        self._serial = None
        self._lock = threading.Lock()
        self._running = False
        self._reader_thread = None

        self.telemetry_pub = rospy.Publisher(self.telemetry_topic, String, queue_size=10)
        rospy.Subscriber(self.cmd_vel_topic, Twist, self.cmd_vel_callback)

        self._connect_serial()
        rospy.on_shutdown(self.shutdown)

    def _connect_serial(self):
        while not rospy.is_shutdown():
            try:
                self._serial = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
                self._running = True
                self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
                self._reader_thread.start()
                rospy.loginfo('Connected to serial port %s @ %s', self.port, self.baudrate)
                return
            except serial.SerialException as exc:
                rospy.logerr('Unable to open serial port %s: %s', self.port, exc)
                rospy.sleep(self.reconnect_delay)

    def cmd_vel_callback(self, msg):
        left_speed = int(max(-255, min(255, msg.linear.x * 200 + msg.angular.z * 100)))
        right_speed = int(max(-255, min(255, msg.linear.x * 200 - msg.angular.z * 100)))
        self.send_drive_command(left_speed, right_speed)

    def send_drive_command(self, left_speed, right_speed):
        packet = '<MOVE,{},{}>\n'.format(left_speed, right_speed)
        self._send_packet(packet)

    def send_stop(self):
        self.send_drive_command(0, 0)

    def _send_packet(self, packet):
        if self._serial is None or not self._serial.is_open:
            rospy.logwarn('Serial port is not open; dropping packet: %s', packet.strip())
            return

        with self._lock:
            try:
                self._serial.write(packet.encode('utf-8'))
                self._serial.flush()
                rospy.loginfo('Sent packet: %s', packet.strip())
            except serial.SerialException as exc:
                rospy.logerr('Serial write failed: %s', exc)

    def _read_loop(self):
        while not rospy.is_shutdown() and self._running and self._serial and self._serial.is_open:
            try:
                line = self._serial.readline().decode('utf-8', errors='replace').strip()
                if not line:
                    continue
                if line.startswith('TELEMETRY,'):
                    msg = String(data=line)
                    self.telemetry_pub.publish(msg)
                    rospy.loginfo('Published telemetry: %s', line)
                else:
                    rospy.logdebug('Unknown serial line: %s', line)
            except serial.SerialException as exc:
                rospy.logerr('Serial read failed: %s', exc)
                break
            except Exception as exc:
                rospy.logerr('Unexpected serial decode error: %s', exc)

    def shutdown(self):
        self._running = False
        self.send_stop()
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1.0)
        if self._serial and self._serial.is_open:
            self._serial.close()


if __name__ == '__main__':
    rospy.init_node('arduino_serial_bridge')
    ArduinoSerialBridge()
    rospy.spin()
