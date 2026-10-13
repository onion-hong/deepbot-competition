#!/usr/bin/python
# coding=gbk

import rospy
import serial
import sys
from std_msgs.msg import String
import sys

#class Voice Assistant Node is design for Bingda offline voice assistant
class VoiceAssistant:
    def __init__(self):
        print(sys.version_info)
        self.device_port = rospy.get_param('~port','/dev/voice_assistant')
        self.voice_cmd_pub = rospy.Publisher('voice_cmd', String, queue_size=1)
        self.voice_cmd_fb_sub = rospy.Subscriber('voice_cmd_fb', String, self.voice_cmd_fb_callback)
        self.py2_flag = True
        if(sys.version_info.major == 3):
            self.py2_flag = False
            print('Not Python2')
        elif(sys.version_info.major == 2):
            self.py2_flag = True
            print('Is Python2')            
        # Serial Communication
        try:
            self.serial = serial.Serial(self.device_port,9600,timeout=10)
            rospy.loginfo("Opening Serial")
            try:
                if self.serial.in_waiting:
                    self.serial.readall()
            except:
                rospy.loginfo("Opening Serial Try Faild")
                pass
        except:
            rospy.logerr("Can not open Serial"+self.device_port)
            self.serial.close
            sys.exit(0)
        outputdata = [0xAA, 0x55, 0xFF, 0x55, 0xAA]
        try:
            while self.serial.out_waiting:
                pass
            self.serial.write(outputdata)
        except:
            rospy.logerr("Command Send Faild")        
        self.func_code = 0
        self.data_code = 0
        self.timer_communication = rospy.Timer(rospy.Duration(100.0/1000),self.timerCommunicationCB)

        self.rate = rospy.Rate(100) # 100hz
        while not rospy.is_shutdown():
            if self.func_code == 1:
                rospy.loginfo("Voice Assistant Connected,Firmware Version %0.1f",self.data_code/10.0)                   
            elif self.func_code == 2:
                if self.data_code == 1:
                    rospy.loginfo("Move Forword")
                    self.voice_cmd_pub.publish('forword')
                if self.data_code == 2:
                    rospy.loginfo("Move Backword")
                    self.voice_cmd_pub.publish('backword')
                if self.data_code == 3:
                    rospy.loginfo("Turn Left")
                    self.voice_cmd_pub.publish('left')
                if self.data_code == 4:
                    rospy.loginfo("Turn Right")
                    self.voice_cmd_pub.publish('right')
                if self.data_code == 0x0a:
                    rospy.loginfo("Turn Straight")
                    self.voice_cmd_pub.publish('straight')                    
                if self.data_code == 5:
                    rospy.loginfo("Stop")
                    self.voice_cmd_pub.publish('stop')
                if self.data_code == 6:
                    rospy.loginfo("Speed UP")
                    self.voice_cmd_pub.publish('speed_up')
                if self.data_code == 7:
                    rospy.loginfo("Speed DOWN")
                    self.voice_cmd_pub.publish('speed_down')     
                if self.data_code == 8:
                    rospy.loginfo("Turn UP")
                    self.voice_cmd_pub.publish('turn_up')
                if self.data_code == 9:
                    rospy.loginfo("Turn DOWN")
                    self.voice_cmd_pub.publish('turn_down') 
            elif self.func_code == 3:
                if self.data_code == 1:
                    rospy.loginfo("Nav To Goal 1")
                    self.voice_cmd_pub.publish('goal_1')                                                                               
                if self.data_code == 2:
                    rospy.loginfo("Nav To Goal 2")
                    self.voice_cmd_pub.publish('goal_2')  
                if self.data_code == 3:
                    rospy.loginfo("Nav To Goal 3")
                    self.voice_cmd_pub.publish('goal_3')  
                if self.data_code == 0xff:
                    rospy.loginfo("Nav Cancel")
                    self.voice_cmd_pub.publish('nav_cancel')  
            elif self.func_code == 4:
                if self.data_code == 1:
                    rospy.loginfo("Actiom Start")
                    self.voice_cmd_pub.publish('action_start')                                                                               
                if self.data_code == 2:
                    rospy.loginfo("Action Start")
                    self.voice_cmd_pub.publish('action_stop')                  
            self.func_code = 0 
            self.data_code = 0                    
            self.rate.sleep()
        outputdata = [0xAA, 0x55, 0xFE, 0x55, 0xAA]
        try:
            while self.serial.out_waiting:
                pass
            self.serial.write(outputdata)
        except:
            rospy.logerr("Command Send Faild")
        rospy.logwarn("Voice Assistant DisConnected")       

    def voice_cmd_fb_callback(self,data):
        invalid_cmd_fb = False
        if data.data == 'forword':
            outputdata = [0xAA, 0x55, 0x01, 0x55, 0xAA]
        elif data.data == 'backword':
            outputdata = [0xAA, 0x55, 0x02, 0x55, 0xAA]
        elif data.data == 'left':
            outputdata = [0xAA, 0x55, 0x03, 0x55, 0xAA]
        elif data.data == 'right':
            outputdata = [0xAA, 0x55, 0x04, 0x55, 0xAA]
        elif data.data == 'stop':
            outputdata = [0xAA, 0x55, 0x05, 0x55, 0xAA]
        elif data.data == 'speed_up':
            outputdata = [0xAA, 0x55, 0x06, 0x55, 0xAA]  
        elif data.data == 'speed_down':
            outputdata = [0xAA, 0x55, 0x07, 0x55, 0xAA]         
        elif data.data == 'turn_up':
            outputdata = [0xAA, 0x55, 0x08, 0x55, 0xAA]  
        elif data.data == 'turn_down':
            outputdata = [0xAA, 0x55, 0x09, 0x55, 0xAA]      
        elif data.data == 'speed_max':
            outputdata = [0xAA, 0x55, 0x0A, 0x55, 0xAA]  
        elif data.data == 'speed_min':
            outputdata = [0xAA, 0x55, 0x0B, 0x55, 0xAA] 
        elif data.data == 'turn_max':
            outputdata = [0xAA, 0x55, 0x0C, 0x55, 0xAA]  
        elif data.data == 'turn_min':
            outputdata = [0xAA, 0x55, 0x0D, 0x55, 0xAA] 
        elif data.data == 'base_not_ready':
            outputdata = [0xAA, 0x55, 0x0F, 0x55, 0xAA] 
        elif data.data == 'nav_faild':
            outputdata = [0xAA, 0x55, 0x21, 0x55, 0xAA] 
        elif data.data == 'goal_cancel':
            outputdata = [0xAA, 0x55, 0x22, 0x55, 0xAA] 
        elif data.data == 'no_goal':
            outputdata = [0xAA, 0x55, 0x23, 0x55, 0xAA] 
        elif data.data == 'nav_not_ready':
            outputdata = [0xAA, 0x55, 0x24, 0x55, 0xAA] 
        elif 'start_nav' in data.data:
            outputdata = [0xAA, 0x55, 0x1F, 0x00, 0x55, 0xAA] 
            if '1' in data.data:
                outputdata[3] = 1
            elif '2' in data.data:
                outputdata[3] = 2
            elif '3' in data.data:
                outputdata[3] = 3
        elif 'goal_reached' in data.data:
            outputdata = [0xAA, 0x55, 0x20, 0x00, 0x55, 0xAA] 
            if '1' in data.data:
                outputdata[3] = 1
            elif '2' in data.data:
                outputdata[3] = 2
            elif '3' in data.data:
                outputdata[3] = 3
        else:
            invalid_cmd_fb = True
        if not invalid_cmd_fb:
            self.serial.write(outputdata)

    #Communication Timer callback to handle receive data
    def timerCommunicationCB(self,event):
        length = self.serial.in_waiting

        if length:
            if self.py2_flag == True:
                data = self.serial.read_all()
                reading = []
                for i in range(length):
                    reading.append(int(data[i].encode('hex'),16)) 
            else:
                reading = self.serial.read_all()
            if len(reading) == 6:  #static data formart,length is 6
                if reading[0] == 0xAA and reading[5] == 0xAA:
                    self.func_code = reading[2]
                    self.data_code = reading[3]
                else:
                    rospy.logwarn("Invalid Data")
        else:
            pass
  
#main function
if __name__=="__main__":
    try:
        rospy.init_node('voice_assistant_node',anonymous=False)
        va = VoiceAssistant()
        rospy.spin()
    except KeyboardInterrupt:    
        va.serial.close
        rospy.loginfo("Shutting down")
