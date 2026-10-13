#!/usr/bin/env python
# coding=utf-8

import rospy
from std_msgs.msg import Int8
from sensor_msgs.msg import Image
from std_msgs.msg import String
from std_msgs.msg import Float32
from riki_msgs.msg import Sonar
import cv2, cv_bridge
import numpy
import os
import sys
from deepbot_auto_driver.msg import DriverMode
import threading
import time
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from vision_msgs.msg import BoundingBox2D, Detection2DArray,ObjectHypothesisWithPose,Detection2D
from dynamic_reconfigure.server import Server
from deepbot_auto_driver.cfg import paramsConfig
import serial



class ControlDriver:
    def __init__(self):

        rospy.init_node("control_drive")

        self.outer_ring_center_target = rospy.get_param('~outer_ring_center_target', 0.26)
        self.outer_ring_vel_z_P = rospy.get_param('~outer_ring_vel_z_P', 0.01) 
        self.outer_ring_vel_z_D = rospy.get_param('~outer_ring_vel_z_D', 0.001) 

        self.Inner_ring_center_target = rospy.get_param('~Inner_ring_center_target', 0.75) 
        self.Inner_ring_vel_y_P = rospy.get_param('~Inner_ring_vel_y_P', 0.001) 
        self.Inner_ring_vel_y_D = rospy.get_param('~Inner_ring_vel_y_D', 0.003) 
        self.Inner_ring_vel_z_P = rospy.get_param('~Inner_ring_vel_z_P', 0.006) 
        self.Inner_ring_vel_z_D = rospy.get_param('~Inner_ring_vel_z_D', 0.001) 

        self.voice_on = rospy.get_param('~voice_on', True)
        
        rate = rospy.Rate(10)

        self.outer_ring_image_x_left = 0
        self.outer_ring_image_x_right = 0.5
        self.outer_ring_image_y_top = 0.5
        self.outer_ring_image_y_bot = 0.8
        self.outer_ring_vel_x = 0.2
        self.outer_ring_vel_y_P = 0
        self.outer_ring_vel_y_D = 0

        self.Inner_ring_mask_x_left = 0.5
        self.Inner_ring_mask_x_right = 1
        self.Inner_ring_mask_y_top = 0.6
        self.Inner_ring_mask_y_bot = 0.85
        self.Inner_ring_vel_x = 0.2
    
        self.pose_z = 0
        
        self.cnt = 0
        self.end_cnt = 0
        self.last_side = 0
        self.last_ring = 0

        self.go_outside_flag = 0

        self.traffic_green_flag = 0
        self.traffic_red_flag = 0
        self.limit_speed_flag = 0
        self.remove_limit_flag = 0
        self.stop_flag = 0

        self.lock_inner = False
        self.lock_end_pos = False
        self.lock_outter = False
        self.traffic_red_lock = False
        self.traffic_green_lock = False
        self.limit_speed_lock = False
        self.remove_limit_lock = False
        self.stop_lock = False
             
        self.sonar_lock = False
        self.sonar_distance = 0.0
        self.measurement_dist = []


        self.driver_mode_pub = rospy.Publisher("/driver_mode", DriverMode, queue_size=1)

        self.cmdvel_pub = rospy.Publisher("/cmd_vel", Twist, queue_size=1)
        self.object_sub = rospy.Subscriber("/detect_node/detections", Detection2DArray, self.ObjectCallback)
        self.odom_sub = rospy.Subscriber("/odom", Odometry, self.odomCallback)
        self.sonar_sub = rospy.Subscriber("/sonar",  Float32,  self.sonarCallback)

        if self.voice_on is True:
            self.device_port = "/dev/voice_assistant"

            try:
                self.serial = serial.Serial(self.device_port,9600,timeout=10)
                print("Opening Serial")
                try:
                    if self.serial.in_waiting:
                        self.serial.readall()
                except:
                    print("Opening Serial Try Faild")
                    pass
            except:
                print("Can not open Serial"+self.device_port)
                self.serial.close
                sys.exit(0)

            self.stop_data = [0xAA, 0x55, 0x05, 0x55, 0xAA]
        
        self.dynamic_reconfigure_server = Server(paramsConfig, self.reconfigCB)
        rospy.on_shutdown(self.shutdown)

        deepbot_driver_way = 0
        side = 0


        drivermode_pub = DriverMode()
        decelerate = Int8()
        msg = Int8()

        while not rospy.is_shutdown(): 
            self.avg_distance = self.get_distance() 
            rospy.loginfo("distance: %f, pose_z: %f", self.avg_distance,  self.pose_z)
            #print(self.avg_distance)      
            if deepbot_driver_way == 0:
                deepbot_driver_way = 2
                side = 2
                #debug mode
                #deepbot_driver_way = 1
                #side = 1
                time.sleep(2)
                drivermode_pub = self.ctrl_data(deepbot_driver_way, side)
                self.driver_mode_pub.publish(drivermode_pub)

            elif deepbot_driver_way == 1:
                if self.cnt % 500 == 0:
                    print("left side")
                side = 1

                if  self.pose_z < -0.6 and self.pose_z > -0.7 and self.lock_end_pos is False:
                    self.lock_end_pos = True
                    print("lock_end_pos start")

                if self.lock_end_pos is True:
                    self.end_cnt = self.end_cnt + 1
                    #print(self.end_cnt)
                    #第二次换线的逻辑,第二次换线的逻辑，根据情况自己修改
                if  self.end_cnt > 78 and self.lock_outter is False :
                    print("start outter line action")
                    self.lock_outter = True
                    car_stop = DriverMode()
                    self.driver_mode_pub.publish(car_stop)
                    carmove = Twist()
                    carmove.linear.x = 0.1
                    carmove.angular.z = -0.5
                    self.cmdvel_pub.publish(carmove)
                    time.sleep(0.5) 
                    side = 2
                    deepbot_driver_way = 2
                    drivermode_pub = self.ctrl_data(deepbot_driver_way, side)
                    self.driver_mode_pub.publish(drivermode_pub)
                    #reset all var and new start
                    self.end_cnt = 0
                    self.stop_lock = False
                    self.stop_flag = 0
                    self.offset  = 0.15



            elif deepbot_driver_way == 2:		
                if self.cnt % 500 == 0:
                    print("right side")
                side = 2

                #超声波检测绕行逻辑，可以根据效果来调试进入这个条件的带数值变量与下面的强制控制车辆运行的逻辑
                if self.avg_distance < 60 and self.avg_distance > 0 and self.sonar_lock is False and self.pose_z > 0.3 :
                    self.sonar_lock = True
                    print("sonar distance  stop")
                    car_stop = DriverMode()
                    self.driver_mode_pub.publish(car_stop)
                    carmove.linear.x = 0.18
                    carmove.angular.z = 0.5
                    self.cmdvel_pub.publish(carmove)
                    time.sleep(2.5) 
                    carmove.linear.x = 0.2
                    carmove.angular.z = -0.5
                    self.cmdvel_pub.publish(carmove)
                    time.sleep(3) 
                    self.driver_way = 2
                    self.side = 2
                    self.drivermode_pub = self.ctrl_data(self.driver_way, self.side)
                    self.driver_mode_pub.publish(self.drivermode_pub)
                    self.lock_inner = False

                    #识别到人行道后停止3秒，然后重新复位所有变量
                if self.stop_flag == 1:
                    self.stop_flag = 0
                    print("stop start action")
                    car_stop = DriverMode()
                    self.driver_mode_pub.publish(car_stop)
                    carmove = Twist()
                    carmove.linear.x = 0
                    carmove.angular.z = 0
                    self.cmdvel_pub.publish(carmove)

                    time.sleep(1)
                    if self.voice_on is True:
                        self.serial.write(self.stop_data)
                    time.sleep(2)
                    deepbot_driver_way = 2
                    side = 2
                    drivermode_pub = self.ctrl_data(deepbot_driver_way, side)
                    self.driver_mode_pub.publish(drivermode_pub)
                    print("reset var")
                    self.lock_end_pos = False
                    self.lock_inner = False
                    self.lock_outter = False
                    self.end_cnt = 0
                    self.lock_inner = True
                    self.sonar_lock = False

                    #第一次强制换线逻辑，如果触发条件不够好，请调整self.pose_z这个值来触发换线进入条件
                if  self.pose_z > -0.98 and self.pose_z < -0.78 and self.lock_inner is False and self.sonar_lock is True:
                    print("start change inner action")
                    self.lock_inner = True
                    car_stop = DriverMode()
                    self.driver_mode_pub.publish(car_stop)
                    carmove = Twist()
                    carmove.linear.x = 0
                    carmove.angular.z = 0
                    self.cmdvel_pub.publish(carmove)
                    carmove = Twist()
                    carmove.linear.x = 0.2
                    carmove.angular.z = 0.5
                    self.cmdvel_pub.publish(carmove)
                    time.sleep(1.2) 
                    side = 1
                    deepbot_driver_way = 1
                    drivermode_pub = self.ctrl_data(deepbot_driver_way, side)
                    self.driver_mode_pub.publish(drivermode_pub)


            self.last_ring = deepbot_driver_way
            self.last_side = side


            self.cnt = self.cnt + 1
            if self.cnt > 50000:
                self.cnt = 0                        

            rate.sleep()
        
        #人行道检测回调函数
    def ObjectCallback(self, msg):
        traffic_id = msg.detections[-1].header.frame_id
        score = msg.detections[-1].results[-1].score
        ptx = msg.detections[-1].bbox.center.x
        pty = msg.detections[-1].bbox.center.y
        ptw = msg.detections[-1].bbox.size_x
        pth = msg.detections[-1].bbox.size_y
        # debug mode
        if traffic_id == "crossing":
            print("crossing:", pth, ptw, pth*ptw)
            #如果停的太远或者太近，请调整这个值(25000)
            if ptw*pth > 25000 and self.stop_lock is False:
                self.stop_flag = 1
                self.stop_lock = True


    def odomCallback(self, odom_msg):
        self.pose_z = odom_msg.pose.pose.orientation.z
        #self.odom_x = odom_msg.pose.pose.position.x
        #if self.cnt % 50 == 0:
           #print("orientation z: %f, end: %d", odom_msg.pose.pose.orientation.z)
           #print(odom_msg.pose.pose.position.x)
           #print(odom_msg.pose.pose.position.y)
        
    def sonarCallback(self, dis_msg):
        self.sonar_distance = dis_msg.data
    
    def get_distance(self):
        if len(self.measurement_dist) >= 5:
            self.measurement_dist.pop(0)


        self.measurement_dist.append(self.sonar_distance)
        if len(self.measurement_dist) < 5:
            return -10
        sorted_measurements = sorted(self.measurement_dist)
        trimmed_data = sorted_measurements[1:-1]  # 去除首尾各一个极值
        #self.avg_distance = sum(trimmed_data) / len(trimmed_data)
        return sum(trimmed_data) / len(trimmed_data)
        #print(self.avg_distance)


       
    def ctrl_data(self, deepbot_driver_way, side):
        drivermode = DriverMode()
        if deepbot_driver_way == 1:
            if side == 1:	#寻左线行驶
                drivermode.mask_x_left = self.outer_ring_image_x_left
                drivermode.mask_x_right = self.outer_ring_image_x_right
                drivermode.mask_y_top = self.outer_ring_image_y_top
                drivermode.mask_y_bot = self.outer_ring_image_y_bot
                drivermode.center_target = self.outer_ring_center_target
                drivermode.vel_x = self.outer_ring_vel_x
                drivermode.vel_y_P = self.outer_ring_vel_y_P
                drivermode.vel_y_D = self.outer_ring_vel_y_D
                drivermode.vel_z_P = self.outer_ring_vel_z_P
                drivermode.vel_z_D = self.outer_ring_vel_z_D
                drivermode.en = 1
        elif deepbot_driver_way == 2:
            if side == 2:	#寻右线行驶
                drivermode.mask_x_left = self.Inner_ring_mask_x_left
                drivermode.mask_x_right = self.Inner_ring_mask_x_right
                drivermode.mask_y_top = self.Inner_ring_mask_y_top
                drivermode.mask_y_bot = self.Inner_ring_mask_y_bot
                drivermode.center_target = self.Inner_ring_center_target
                drivermode.vel_x = self.Inner_ring_vel_x
                drivermode.vel_y_P = self.Inner_ring_vel_y_P
                drivermode.vel_y_D = self.Inner_ring_vel_y_D
                drivermode.vel_z_P = self.Inner_ring_vel_z_P
                drivermode.vel_z_D = self.Inner_ring_vel_z_D
                drivermode.en = 4
        return drivermode
            

    def reconfigCB(self, config, level):
        self.outer_ring_center_target = config.outer_ring_center_target
        self.outer_ring_vel_z_P = config.outer_ring_vel_z_P
        self.outer_ring_vel_z_D = config.outer_ring_vel_z_D

        self.Inner_ring_center_target = config.Inner_ring_center_target
        self.Inner_ring_vel_y_P = config.Inner_ring_vel_y_P
        self.Inner_ring_vel_y_D = config.Inner_ring_vel_y_D
        self.Inner_ring_vel_z_P = config.Inner_ring_vel_z_P
        self.Inner_ring_vel_z_D = config.Inner_ring_vel_z_D 

        if self.last_ring != 0:
            drivermode_pub = self.ctrl_data(self.last_ring, self.last_side)
            self.driver_mode_pub.publish(drivermode_pub)

        return config
    
    def shutdown(self):
        carmove = Twist()
        carmove.linear.x = 0
        carmove.angular.z = 0
        self.cmdvel_pub.publish(carmove)
        self.cmdvel_pub.publish(carmove)
        rospy.logwarn("now will shutdown cmd_vel ...")



if __name__ == '__main__':
    try:
        driver = ControlDriver()
        rospy.spin()
    except rospy.ROSInterruptException:
    	pass
