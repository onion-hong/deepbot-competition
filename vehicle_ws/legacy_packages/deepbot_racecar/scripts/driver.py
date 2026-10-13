#!/usr/bin/env python3
# coding=utf-8

import rospy
import os
from sensor_msgs.msg import Image
import cv2
import numpy as np
import time
from geometry_msgs.msg import Twist
from std_msgs.msg import Int8
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
#from PIL import PImage
import PIL.Image
from vision_msgs.msg import BoundingBox2D, Detection2DArray,ObjectHypothesisWithPose,Detection2D
import serial


class AutoPilot(nn.Module):
    def __init__(self):
        super().__init__()
        self.cnn = nn.Sequential(
            nn.Conv2d(3, 24, 5, stride=2),  # 输入通道3
            nn.ReLU(),
            nn.Conv2d(24, 36, 5, stride=2),
            nn.ReLU(),
            nn.Conv2d(36, 48, 5, stride=2),
            nn.ReLU(),
            nn.Flatten()  # 自动展平
        )
        
        # 动态计算全连接层输入
        with torch.no_grad():
            dummy = torch.randn(1, 3, 120, 160)  # 注意H,W顺序
            features = self.cnn(dummy)
            in_features = features.shape[1]
            
        self.fc = nn.Sequential(
            nn.Linear(in_features, 100),
            nn.ReLU(),
            nn.Linear(100, 50),
            nn.ReLU(),
            nn.Linear(50, 1)
        )

    def forward(self, x):
        x = self.cnn(x)
        return self.fc(x)

class Driver:
    def __init__(self):

        self.model = AutoPilot()
        dir_path = os.path.dirname(os.path.realpath(__file__))
        self.model_path = dir_path + "/autopilot.pth"
        rospy.loginfo("path: %s", self.model_path)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model.load_state_dict(torch.load(self.model_path, map_location='cpu'))
        self.model.eval()
        
        self.transform = transforms.Compose([
                transforms.Resize((120, 160)),  # 保持原始尺寸
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406],  # ImageNet标准化
                                    std=[0.229, 0.224, 0.225])
            ])

        self.speed_x = rospy.get_param('~speed_x', 0.2)
        self.voice_on = rospy.get_param('~voice_on', True)
        self.camera_topic = rospy.get_param('~camera_topic', '/camera/rgb/image_raw/')

        self.image_sub = rospy.Subscriber(self.camera_topic, Image, self.image_callback)
        self.object_sub = rospy.Subscriber("/detect_node/detections", Detection2DArray, self.ObjectCallback)

        self.cmd_vel_pub = rospy.Publisher("/cmd_vel", Twist, queue_size=1)
        rate = rospy.Rate(20)

        self.stop_flag = 0
        self.stop_lock = False
        self.start_lock = False

        self.cv_image = None

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


        rospy.on_shutdown(self.shutdown)
        carmove = Twist()
        while not rospy.is_shutdown():
            if self.cv_image is not None:
                if self.stop_flag == 0:
                    steering = self.predict(self.cv_image) 
                    carmove.angular.z = round(steering, 2)  
                    if abs(steering) > 0.8:
                        carmove.linear.x =  round(self.speed_x*0.8, 2)
                    else:
                        carmove.linear.x = self.speed_x
                    #print(carmove.angular.z, carmove.linear.x) 
                    self.cmd_vel_pub.publish(carmove)
                else:
                    carmove.linear.x =  0
                    carmove.angular.z = 0 
                    print(carmove.angular.z, carmove.linear.x) 
                    self.cmd_vel_pub.publish(carmove)
                    self.cmd_vel_pub.publish(carmove)
                    self.cmd_vel_pub.publish(carmove)
                    time.sleep(1)
                    if self.voice_on is True:
                        self.serial.write(self.stop_data)
                    time.sleep(2)
                    self.stop_flag = 0

                image = cv2.resize(self.cv_image, (160, 120))
                cv2.imshow('Capture', image)
                if cv2.waitKey(1) == ord('q'):
                    break
            rate.sleep()

    def image_callback(self, msg):
        color_image = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.width, -1)
        self.cv_image = cv2.cvtColor(color_image, cv2.COLOR_BGR2RGB)
        
    def predict(self, image):
        image = cv2.resize(image, (160, 120))
        image = PIL.Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        image_tensor = self.transform(image).unsqueeze(0)
        
        with torch.no_grad():
            prediction = self.model(image_tensor)
        
        return prediction.item()

      
    def ObjectCallback(self, msg):
        traffic_id = msg.detections[-1].header.frame_id
        score = msg.detections[-1].results[-1].score
        ptx = msg.detections[-1].bbox.center.x
        pty = msg.detections[-1].bbox.center.y
        ptw = msg.detections[-1].bbox.size_x
        pth = msg.detections[-1].bbox.size_y
        print(score)

        if traffic_id == "crossing":
            print("crossing:", pth, ptw, pth*ptw)
            if ptw*pth > 25000 and self.stop_lock is False:
                 self.stop_flag = 1
                 self.stop_lock = True
                 self.start_lock = False

        if traffic_id == "start":
            print("start:", pth, ptw, pth*ptw)
            if ptw*pth > 20000 and self.start_lock is False:
                 self.stop_lock = False
                 self.stop_flag = 0
                 self.start_lock = True
    
    def shutdown(self):
        carmove = Twist()
        carmove.linear.x = 0
        carmove.angular.z = 0
        self.cmd_vel_pub.publish(carmove)
        self.cmd_vel_pub.publish(carmove)
        rospy.logwarn("now will shutdown cmd_vel ...")


if __name__ == '__main__':
    try:
        rospy.init_node("deep car")
        drvier = Driver()
        rospy.spin()
    except rospy.ROSInterruptException:
        pass




