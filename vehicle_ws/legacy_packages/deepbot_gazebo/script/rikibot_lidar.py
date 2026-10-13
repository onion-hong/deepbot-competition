#!/usr/bin/env python
# -*- coding: utf-8 -*-


import rospy
import numpy as np
import math
from sensor_msgs.msg import LaserScan
from std_msgs.msg import UInt8, Float64, Bool


class DetectObstacle():
    def __init__(self):

        self.obstacle_distance = rospy.get_param("~detect_distance", 0.5)
        self.sub_scan = rospy.Subscriber('/scan', LaserScan, self.FindObstacle, queue_size=1)

    def FindObstacle(self, scan):
        angle_scan = 15
        scan_start = 180 - angle_scan
        scan_end = 180 + angle_scan
        obstacle_count = 0
        for i in range(scan_start, scan_end):
            if scan.ranges[i] < self.obstacle_distance and scan.ranges[i] > 0.01:
                obstacle_count = obstacle_count + 1

        if obstacle_count > 5 :
            rospy.loginfo("detect obstacle front")
                
        #print obstacle_count, obstacle_existence


    def main(self):
        rospy.spin()

if __name__ == '__main__':
    rospy.init_node('detect_obstacle')
    node = DetectObstacle()
    node.main()



















