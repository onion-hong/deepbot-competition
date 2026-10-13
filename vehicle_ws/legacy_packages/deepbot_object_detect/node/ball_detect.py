#!/usr/bin/env python
# _*_ coding:utf-8 _*_

import rospy
import numpy as np
import os,cv2
import math
import imutils

from cv_bridge import CvBridge, CvBridgeError
from sensor_msgs.msg import Image, CompressedImage
from vision_msgs.msg import BoundingBox2D


class BallDetect():
    def __init__(self):
        rospy.init_node('xtrobot_ball_detect_node', log_level=rospy.INFO)
        self.rate = rospy.get_param('~rate', 20)
        self.camera_topic = rospy.get_param('~camera_topic', '/camera/rgb/image_raw/')
        r = rospy.Rate(self.rate)
        self.name = rospy.get_name()
        rospy.on_shutdown(self.shutdown)

        self.sub_image_type = "raw"
        self.pub_face_type = "raw"
        self.cv_image = None

        #green ball
        #self.ballLower = np.array((45, 100, 30))
        #self.ballUpper = np.array((65, 256, 256))
        #blue ball
        #self.ballLower = np.array((135, 79, 63))
        #self.ballUpper = np.array((179, 255, 255))
        self.ballLower = np.array((12, 33, 0))
        self.ballUpper = np.array((179, 255, 255))
        #red ball
        #self.ballLower = np.array((0, 162, 167))
        #self.ballUpper = np.array((179, 255, 255))


        if self.sub_image_type == "compressed":
            self.sub_image_original = rospy.Subscriber(self.camera_topic+'compressed', CompressedImage, self.ImageCallback, queue_size = 1)
        elif self.sub_image_type == "raw":
            self.sub_image_original = rospy.Subscriber(self.camera_topic, Image, self.ImageCallback, queue_size = 1)


        if self.pub_face_type == "compressed":
            self.pub_face_image = rospy.Publisher('/object_image/compressed', CompressedImage, queue_size=1)
        else:
            self.pub_face_image = rospy.Publisher('/object_image', Image, queue_size=1)

        self.pub_bbox = rospy.Publisher("/detect_bbox", BoundingBox2D,  queue_size=1)

        self.cvBridge = CvBridge()
	center = None
       

        while not rospy.is_shutdown():

            # Resize frame of video to 1/4 size for faster face recognition processing
            if self.cv_image is not None:
		blurred = cv2.GaussianBlur(self.cv_image, (5, 5), 0)
        	hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
        	erode_hsv = cv2.erode(hsv, None, iterations=2)
		mask = cv2.inRange(erode_hsv, self.ballLower, self.ballUpper)
                #kernel = np.ones((5, 5), np.uint8)
        	#mask = cv2.dilate(mask, kernel, iterations=2)
  		cnts = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[-2]
        	#cnts = imutils.grab_contours(cnts)
		if len(cnts) > 0:
		    # find the largest contour in the mask, then use
		    # it to compute the minimum enclosing circle and
		    # centroid
		    c = max(cnts, key=cv2.contourArea)
                    rect = cv2.minAreaRect(c)
                    box = cv2.boxPoints(rect)
                    cv2.drawContours(self.cv_image, [np.int0(box)], -1, (0, 255, 255), 2)
                    cx, cy = rect[0]
                    h, w = rect[1]
                    self.c_angle = rect[2]

		    # only proceed if the radius meets a minimum size
		    if h*w > 2000:
			# draw the circle and centroid on the frame,
			# then update the list of tracked points
                        cv2.circle(self.cv_image, (int(cx), int(cy)), 3, (216, 0, 255), -1)
                        bbox = BoundingBox2D()
                        bbox.center.x = cx
                        bbox.center.y = cy
                        bbox.size_x = w
                        bbox.size_y = h

                    	self.pub_bbox.publish(bbox)

	        if self.pub_face_type == "compressed":
                # publishes traffic sign image in compressed type
                    self.pub_face_image.publish(self.cvBridge.cv2_to_compressed_imgmsg(self.cv_image, "jpg"))

                elif self.pub_face_type == "raw":
                # publishes traffic sign image in raw type
                    self.pub_face_image.publish(self.cvBridge.cv2_to_imgmsg(self.cv_image, "bgr8"))
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
        rospy.logwarn("now will shutdown face_location_node ...")

if __name__ == '__main__':
    try:
        detect = BallDetect()
        rospy.spin()
    except Exception, e:
        rospy.logerr("%s", str(e))
        os._exit(1)

