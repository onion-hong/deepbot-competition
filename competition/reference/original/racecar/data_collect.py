#!/usr/bin/env python
# -*- coding: utf-8 -*-

import rospy
import numpy as np
import math
import os,sys, time
import cv2
import cv_bridge
import csv
from shutil import copy, rmtree
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Image


class DataCollect():
    def __init__(self):
        self.rate = rospy.get_param('~rate', 10)
        r = rospy.Rate(self.rate)

        self.steeringAngle = 0.0
        self.throttle = 0.0

        self.save_dir = "/home/deepbot/Work/train_data"
        self.bridge = cv_bridge.CvBridge()
        self.cv_image = None
       
        self.odom_sub = rospy.Subscriber("/odom", Odometry, self.odomCallback);

        self.camera_topic = rospy.get_param('~camera_topic', '/camera/rgb/image_raw/')
        self.image_sub = rospy.Subscriber(self.camera_topic, Image, self.image_callback)

        if os.path.exists(self.save_dir):
            rmtree(self.save_dir)
        os.makedirs(self.save_dir)

        self.csv_file = open(f'{self.save_dir}/data.csv', 'w', newline='')
        self.writer = csv.writer(self.csv_file)
        self.writer.writerow(['image_path', 'steering'])
        rospy.loginfo("dir : %s", self.save_dir)
        #self.mask = self.create_mask()
            
        while not rospy.is_shutdown():
            if abs(self.throttle) > 0.02 or abs(self.steeringAngle) > 0.02:
                if self.cv_image is not None:
                    timestamp = int(time.time()*1000)
                    img_path = f'{self.save_dir}/{timestamp}.jpg'
                    processed = self.process_image(self.cv_image)
                    cv2.imwrite(img_path, processed)
                    throttle = self.throttle
                    steering = self.steeringAngle
                    self.writer.writerow([img_path, steering])
                    cv2.imshow('Capture', processed)
                    if cv2.waitKey(1) == ord('q'):
                        break
            r.sleep()


    def process_image(self, image):
        """图像预处理"""
        #gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        #masked = cv2.bitwise_and(gray, mask)
        resized = cv2.resize(image, (160, 120))
        return resized

    def image_callback(self, msg):
        self.cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        

    def odomCallback(self, msg):		
        self.throttle = round(msg.twist.twist.linear.x, 4)
        self.steeringAngle = round(msg.twist.twist.angular.z, 4)

  
    def main(self):
        rospy.spin()

if __name__ == '__main__':
    rospy.init_node('Data Collect')
    node = DataCollect()
    node.main()


