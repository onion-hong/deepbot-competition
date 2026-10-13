#!/usr/bin/env python
# _*_ coding:utf-8 _*_

import rospy
import numpy as np
import os,cv2
import math
import imutils
from geometry_msgs.msg import Twist
from cv_bridge import CvBridge, CvBridgeError
from sensor_msgs.msg import Image, CompressedImage


class RikibotDetect():
    def __init__(self):
        rospy.init_node('rikibot_detect_node', log_level=rospy.INFO)
        self.rate = rospy.get_param('~rate', 20)
        self.camera_topic = rospy.get_param('~camera_topic', '/camera/rgb/image_raw/')
        r = rospy.Rate(self.rate)
        self.name = rospy.get_name()
        rospy.on_shutdown(self.shutdown)

        self.sub_image_type = "raw"
        self.pub_face_type = "raw"
        self.cv_image = None

        self.color_dist = {'red': {'Lower': np.array([16, 101, 171]), 'Upper': np.array([77, 255, 255])},
              'green': {'Lower': np.array([35, 43, 35]), 'Upper': np.array([90, 255, 255])},
              }

        self.vel_pub = rospy.Publisher('/cmd_vel', Twist, queue_size=5)


        if self.sub_image_type == "compressed":
            self.sub_image_original = rospy.Subscriber(self.camera_topic+'compressed', CompressedImage, self.ImageCallback, queue_size = 1)
        elif self.sub_image_type == "raw":
            self.sub_image_original = rospy.Subscriber(self.camera_topic, Image, self.ImageCallback, queue_size = 1)


        self.cvBridge = CvBridge()
	center = None
       

        while not rospy.is_shutdown():
            if self.cv_image is not None:
		blurred = cv2.GaussianBlur(self.cv_image, (5, 5), 0)
        	hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
                for i in self.color_dist:
                    mask = cv2.inRange(hsv, self.color_dist[i]['Lower'], self.color_dist[i]['Upper'])
                    mask = cv2.erode(mask, None, iterations=2)
                    kernel = np.ones((5, 5), np.uint8)
                    mask = cv2.dilate(mask, kernel, iterations=2)
                    cnts = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[-2]
                    if len(cnts) > 0:
                        # 找出最大的区域
                        c = max(cnts, key=cv2.contourArea)
                        # 返回的值 中心坐标（x, y）,（w，h）,角度
                        rect = cv2.minAreaRect(c)
                        # 获取最小外接矩形的4个顶点
                        box = cv2.boxPoints(rect)
                        # 数据类型转换
                        # 绘制轮廓
                        cv2.drawContours(self.cv_image, [np.int0(box)], -1, (0, 255, 255), 2)
                        # 找色块中心点
                        c_x, c_y = rect[0]
                        h, w = rect[1]
                        self.c_angle = rect[2]
                        #print(h*w)
                        if h * w >= 1000:   # 色块面积限制
                             cv2.circle(self.cv_image, (int(c_x), int(c_y)), 3, (216, 0, 255), -1)

                cv2.imshow("detect", self.cv_image), cv2.waitKey(1)


            r.sleep()


    def ImageCallback(self, image_msg):
        if self.sub_image_type == "compressed":
            #converting compressed image to opencv image
            np_arr = np.fromstring(image_msg.data, np.uint8)
            self.cv_image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        elif self.sub_image_type == "raw":
            self.cv_image = self.cvBridge.imgmsg_to_cv2(image_msg, "bgr8")


    def shutdown(self):
        # Release handle to the webcam
        rospy.logwarn("now will shutdown rikibot detect node ...")

if __name__ == '__main__':
    try:
        detect = RikibotDetect()
        rospy.spin()
    except Exception, e:
        rospy.logerr("%s", str(e))
        os._exit(1)

