"""Minimal OpenCV window that subscribes to a ROS 2 Image topic.

Launch via ros2 run or include in a launch file:
    ros2 run robot_control stream_viewer \
        --ros-args -r image:=/rock64_1/camera/image_raw

Needs a display (X server / WSLg). Without one — e.g. a bare WSL terminal —
it falls back to a headless mode that logs frame info instead of crashing.
Open the ESP32 stream in a browser (http://<camera-ip>/stream) for video.
"""
import os

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image

try:
    from cv_bridge import CvBridge
    import cv2
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False


def has_display() -> bool:
    """True if a GUI display looks available (X11 or Wayland)."""
    return bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))


class StreamViewer(Node):
    WINDOW = 'Rock64 Camera'

    def __init__(self):
        super().__init__('stream_viewer')
        if not _CV2_AVAILABLE:
            self.get_logger().error(
                'cv2 or cv_bridge not installed — cannot display images.'
            )
            return
        self.headless = not has_display()
        self._warned_headless = False
        self.bridge = CvBridge()
        self.create_subscription(Image, 'image', self._callback, 1)
        if self.headless:
            self.get_logger().warning(
                'No display detected ($DISPLAY unset) — running headless. '
                'Camera frames will not be shown in a window. '
                'Open http://<camera-ip>/stream in a browser to view video, '
                'or set up a display (WSLg / VcXsrv).'
            )
        else:
            self.get_logger().info(
                'Stream viewer waiting for images on "image" topic'
            )

    def _callback(self, msg: Image):
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception as exc:
            self.get_logger().error(f'cv_bridge conversion failed: {exc}')
            return

        if self.headless:
            if not self._warned_headless:
                self.get_logger().info(
                    'Receiving camera frames (%dx%d) — headless, not '
                    'displaying.', msg.width, msg.height,
                )
                self._warned_headless = True
            return

        try:
            cv2.imshow(self.WINDOW, frame)
            key = cv2.waitKey(1)
        except cv2.error as exc:
            self.headless = True
            self.get_logger().warning(
                'Display unavailable (%s) — switching to headless mode. '
                'Open http://<camera-ip>/stream in a browser for video.',
                exc,
            )
            return
        if key == 27:  # Esc
            self.get_logger().info('Esc pressed — shutting down viewer.')
            raise SystemExit(0)

    def destroy_node(self):
        if _CV2_AVAILABLE:
            try:
                cv2.destroyAllWindows()
            except cv2.error:
                pass
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = StreamViewer()
    try:
        rclpy.spin(node)
    except SystemExit:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
