"""Minimal OpenCV window that subscribes to a ROS 2 Image topic.

Launch via ros2 run or include in a launch file:
    ros2 run robot_control stream_viewer \
        --ros-args -r image:=/rock64_1/camera/image_raw
"""
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image

try:
    from cv_bridge import CvBridge
    import cv2
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False


class StreamViewer(Node):
    WINDOW = 'Rock64 Camera'

    def __init__(self):
        super().__init__('stream_viewer')
        if not _CV2_AVAILABLE:
            self.get_logger().error(
                'cv2 or cv_bridge not installed — cannot display images.'
            )
            return
        self.bridge = CvBridge()
        self.create_subscription(Image, 'image', self._callback, 1)
        self.get_logger().info('Stream viewer waiting for images on "image" topic')

    def _callback(self, msg: Image):
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception as exc:
            self.get_logger().error(f'cv_bridge conversion failed: {exc}')
            return

        cv2.imshow(self.WINDOW, frame)
        key = cv2.waitKey(1)
        if key == 27:  # Esc
            self.get_logger().info('Esc pressed — shutting down viewer.')
            raise SystemExit(0)

    def destroy_node(self):
        if _CV2_AVAILABLE:
            cv2.destroyAllWindows()
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
