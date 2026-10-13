#!/usr/bin/env python
# coding=utf-8

import rospy
import os
import math
import threading
import time
from sensor_msgs.msg import Image
import cv2, cv_bridge
import numpy
from time import sleep
from geometry_msgs.msg import Twist
from std_msgs.msg import Int8
from deepbot_auto_driver.msg import DriverMode

class Follower:
    def __init__(self):
        # Adapted from factory auto_run.py; keep its ROI / centroid / P-D algorithm.
        self.lock = threading.RLock()
        self.last_image_time = None
        self.have_error = False
        self.mode_signature = None
        self.show_image = rospy.get_param('~show_image', False)
        self.max_speed = float(rospy.get_param('~max_speed', 0.025))
        self.max_angular = float(rospy.get_param('~max_angular', 0.08))
        self.image_timeout = float(rospy.get_param('~image_timeout', 0.5))
        if not (math.isfinite(self.max_speed) and 0 < self.max_speed <= 0.04
                and math.isfinite(self.max_angular) and 0 < self.max_angular <= 0.08
                and math.isfinite(self.image_timeout) and 0.1 <= self.image_timeout <= 0.5):
            raise ValueError('Invalid practice limits')
        self.bridge = cv_bridge.CvBridge()
        #cv2.namedWindow("window", 1)
        # 订阅usb摄像头
        self.hue_black = (0,0,0,180,255,46)# black
        self.hue_red = (0,50,60,14,255,255)# red
        self.hue_blue = (100,43,46,124,255,255)# blue
        self.hue_green= (35,43,46,77,255,255)# green
        #self.hue_yellow = (24,65,190,36,255,255)# yellow
        #self.hue_yellow = (14,52,82,102,255,255)# yellow-old
        self.hue_yellow = (22,57,139,85,187,255)# yellow-ck250603-night

        self.huanxian = Int8()
        self.outside = Int8()
        self.huanxian.data = 0
        self.outside.data = 0

        self.last_erro=0
        self.mask_x_left = 1.0000
        self.mask_x_right = 1.0000
        self.mask_y_top = 1.0000
        self.mask_y_bot = 1.0000
        self.center_target = 0.5
        self.vel_x = 0.0000
        self.vel_y_P = 0.0000
        self.vel_y_D = 0.0000
        self.vel_z_P = 0.0000
        self.vel_z_D = 0.0000
        self.state = 0
        self.state_last = 0

        self.twist = Twist()

        self.camera_topic = rospy.get_param('~camera_topic', '/camera_720_trial/image_raw_decoded')
        self.cmd_vel_pub = rospy.Publisher(
            rospy.get_param('~cmd_topic', '/cmd_vel_factory_trial'), Twist, queue_size=1)
        self.go_outside_pub = rospy.Publisher("/outside_flag", Int8, queue_size=1)
        rospy.on_shutdown(self.stop_output)
        self.timer = rospy.Timer(rospy.Duration(0.1), self.check_image_timeout)
        self.image_sub = rospy.Subscriber(self.camera_topic, Image, self.image_callback,
                                          queue_size=1, buff_size=4 * 1024 * 1024)
        self.driver_mode_sub = rospy.Subscriber(
            rospy.get_param('~mode_topic', '/factory_driver_mode'), DriverMode,
            self.driver_mode_callback, queue_size=1)


    def image_callback(self, msg):
        with self.lock:
            try:
                if msg.header.stamp.to_sec() != 0:
                    age = (rospy.Time.now() - msg.header.stamp).to_sec()
                    if age > self.image_timeout or age < -0.1:
                        self.stop_output()
                        return
                image1 = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
                self.process_image(image1)
            except (cv_bridge.CvBridgeError, cv2.error, ValueError, TypeError) as exc:
                self.stop_output()
                rospy.logwarn_throttle(2, 'Factory image rejected: %s', str(exc))

    def process_image(self, image1):
		
        image = cv2.resize(image1, (320,240), interpolation=cv2.INTER_AREA)
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

        lowerbH = self.hue_yellow[0]
        lowerbS = self.hue_yellow[1]
        lowerbV = self.hue_yellow[2]
        upperbH = self.hue_yellow[3]
        upperbS = self.hue_yellow[4]
        upperbV = self.hue_yellow[5]

        mask1 = cv2.inRange(hsv,(lowerbH,lowerbS,lowerbV),(upperbH,upperbS,upperbV))
        #mask1 = cv2.inRange(hsv,(lowerbH,lowerbS,lowerbV),(upperbH,upperbS,upperbV))
        #mask2 = cv2.inRange(hsv,(lowerbH+165,lowerbS,lowerbV),(upperbH+170,upperbS,upperbV))
        #mask = cv2.bitwise_or(mask1, mask2)
        mask = mask1

        h, w, d = image.shape       
        search_top = h*self.mask_y_top
        search_bot = h*self.mask_y_bot
        mask[0:int(search_top), 0:w] = 0
        mask[int(search_bot):h, 0:w] = 0
        mask[0:h, 0:int(self.mask_x_left*w)] = 0
        mask[0:h, int(self.mask_x_right*w):w] = 0

        self.last_image_time = time.monotonic()
        self.twist = Twist()
        self.last_z = 0
        
        # 计算mask图像的重心，即几何中心
        M = cv2.moments(mask)
        if M['m00'] > 0 and self.state in (1, 4):
            cx = int(M['m10']/M['m00'])
            cy = int(M['m01']/M['m00'])
            cv2.circle(image, (cx, cy), 10, (0, 255, 0), -1)

            # 计算图像中心线和目标指示线中心的距离；保留原厂像素误差P/D。
            erro = cx - w*self.center_target
            d_erro = erro - self.last_erro if self.have_error else 0.0
            self.twist.linear.x = min(self.vel_x, self.max_speed)
            requested_z = -float(erro)*self.vel_z_P-float(d_erro)*self.vel_z_D
            self.last_z = self.twist.angular.z = max(-self.max_angular, min(self.max_angular, requested_z))
            self.state_last = self.state
            self.last_erro = erro
            self.have_error = True
            if cx > 80 and 140 < cy < 165 and self.state == 4:
                self.outside.data = 1
                for _ in range(4):
                    self.go_outside_pub.publish(self.outside)
        else:
            self.have_error = False
            self.last_erro = 0
        self.cmd_vel_pub.publish(self.twist)
        if self.state > 0:
            if self.state == 1:
                cv2.putText(mask, "out_way", (0,30),cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255),1)
            elif self.state == 4:
                cv2.putText(mask, "in_way", (0,30),cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255),1)
        else :
            cv2.putText(mask, "no_line_init", (0,30),cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255),1)

        if self.show_image:
            cv2.imshow("watch_line", mask)
            cv2.waitKey(1)
        #cv2.imshow("watch_line1", mask1)
        #cv2.imshow("watch_detect", image)

    def stop_output(self):
        with self.lock:
            self.twist = Twist()
            self.have_error = False
            self.last_erro = 0
            self.cmd_vel_pub.publish(self.twist)

    def check_image_timeout(self, event):
        with self.lock:
            if self.last_image_time is None or time.monotonic() - self.last_image_time > self.image_timeout:
                self.stop_output()

    def driver_mode_callback(self, msg): 
        fields = ('mask_x_left', 'mask_x_right', 'mask_y_top', 'mask_y_bot',
                  'center_target', 'vel_x', 'vel_y_P', 'vel_y_D', 'vel_z_P', 'vel_z_D')
        with self.lock:
            values = [getattr(msg, name) for name in fields]
            valid = (all(math.isfinite(v) for v in values)
                     and 0 <= msg.mask_x_left < msg.mask_x_right <= 1
                     and 0 <= msg.mask_y_top < msg.mask_y_bot <= 1
                     and 0 <= msg.center_target <= 1 and msg.vel_x >= 0
                     and 0 <= msg.vel_z_P <= 0.02 and 0 <= msg.vel_z_D <= 0.01
                     and msg.en in (1, 4))
            signature = tuple(values) + (msg.en,)
            if not valid:
                self.state = 0
                self.mode_signature = None
                self.stop_output()
                return
            if signature != self.mode_signature:
                self.stop_output()
            for name, value in zip(fields, values):
                setattr(self, name, value)
            self.state = msg.en
            self.mode_signature = signature

if __name__ == '__main__':
    try:
        rospy.init_node("factory_line_follower_practice")
        follower = Follower()
        rospy.spin()
    except rospy.ROSInterruptException:
        pass




