#!/usr/bin/env python3

import rospy
import cv2
from cv_bridge import CvBridge
from sensor_msgs.msg import Image


def main():
    rospy.init_node('esp32_camera_bridge')

    camera_url = rospy.get_param('~camera_url', 'http://192.168.4.1/stream')
    camera_topic = rospy.get_param('~camera_topic', '/camera/image_raw')
    frame_id = rospy.get_param('~frame_id', 'camera')
    publish_rate = rospy.get_param('~publish_rate', 10.0)

    bridge = CvBridge()
    publisher = rospy.Publisher(camera_topic, Image, queue_size=1)
    rate = rospy.Rate(publish_rate)
    cap = None

    rospy.loginfo('Starting ESP32 camera bridge to %s', camera_url)

    while not rospy.is_shutdown():
        if cap is None or not cap.isOpened():
            if cap is not None:
                cap.release()
            cap = cv2.VideoCapture(camera_url)
            if not cap.isOpened():
                rospy.logwarn('Unable to open camera stream: %s', camera_url)
                rospy.sleep(2.0)
                continue
            rospy.loginfo('Connected to camera stream: %s', camera_url)

        grabbed, frame = cap.read()
        if not grabbed:
            rospy.logwarn_throttle(5.0, 'No frame received from camera stream')
            rate.sleep()
            continue

        try:
            msg = bridge.cv2_to_imgmsg(frame, encoding='bgr8')
            msg.header.stamp = rospy.Time.now()
            msg.header.frame_id = frame_id
            publisher.publish(msg)
            rospy.logdebug('Published image frame %dx%d', frame.shape[1], frame.shape[0])
        except Exception as exc:
            rospy.logerr('Failed to convert camera frame: %s', exc)

        rate.sleep()

    if cap is not None:
        cap.release()


if __name__ == '__main__':
    try:
        main()
    except rospy.ROSInterruptException:
        pass
