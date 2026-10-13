#!/usr/bin/python
# coding=gbk

import rospy
import math
from std_msgs.msg import String
from geometry_msgs.msg import Twist
from move_base_msgs.msg import MoveBaseActionResult
from geometry_msgs.msg import PoseStamped
from actionlib_msgs.msg import GoalID

#class Voice Assistant Node is design for Bingda offline voice assistant
class ArtificialIdiot:
    def __init__(self):
        self.last_voice_time = rospy.Time.now()
        self.last_move_cmd_time = rospy.Time.now()
        self.twist = Twist()
        self.voice_cmd_sub = rospy.Subscriber('voice_cmd', String, self.voice_cmd_callback)
        self.voice_cmd_fb_pub = rospy.Publisher('voice_cmd_fb', String, queue_size=1)
        self.cmd_pub = rospy.Publisher('cmd_vel', Twist, queue_size=10)
        self.nav_result_sub = rospy.Subscriber('move_base/result', MoveBaseActionResult, self.nav_status_callback, queue_size=10)
        self.nav_goal_pub = rospy.Publisher('move_base_simple/goal', PoseStamped, queue_size=1) 
        self.nav_cancel_pub = rospy.Publisher('move_base/cancel', GoalID, queue_size=1)        
        self.line_speed_x = 0.2
        self.angle_speed_z = 0.5
        self.pose_stamped = PoseStamped()
        self.pose_stamped.header.frame_id = "map"
        self.goal_list = [[1.0,1.0,0.0],[0.0,0.0,0.0]]
        self.goal_id = 0
        self.nav_working = 0
        self.cmd_vel_sub_number = 0
        self.nav_goal_sub_number = 0
        self.cmd_pub.get_num_connections()
        self.rate = rospy.Rate(100) # 100hz

        while not rospy.is_shutdown():
            self.cmd_vel_sub_number = self.cmd_pub.get_num_connections()
            self.nav_goal_sub_number = self.nav_goal_pub.get_num_connections()
            if (rospy.Time.now() - self.last_move_cmd_time).to_sec() < 5.0:
                if self.twist.linear.x > 0:
                    self.twist.linear.x = self.line_speed_x
                elif self.twist.linear.x < 0:
                    self.twist.linear.x = self.line_speed_x*-1.0
                else:
                    pass
                if self.twist.angular.z > 0:
                    self.twist.angular.z = self.angle_speed_z
                elif self.twist.angular.z < 0:
                    self.twist.angular.z = self.angle_speed_z*-1.0
                else:
                    pass
                self.cmd_pub.publish(self.twist)
            else:
                self.twist.linear.x = 0
                self.twist.angular.z = 0
                # self.cmd_pub.publish(self.twist)

            if self.goal_id != 0 and self.nav_working == 0:
                if self.nav_goal_sub_number == 0:
                    self.voice_cmd_fb_pub.publish('nav_not_ready')
                    self.goal_id = 0
                else:
                    if len(self.goal_list) >= self.goal_id:
                        self.pose_stamped.header.stamp = rospy.Time.now()
                        self.pose_stamped.pose.position.x = self.goal_list[self.goal_id-1][0]
                        self.pose_stamped.pose.position.y = self.goal_list[self.goal_id-1][1]
                        if abs(self.goal_list[self.goal_id-1][2]) > 1.0:
                            self.pose_stamped.pose.orientation.z = 0.0
                            self.pose_stamped.pose.orientation.w = 1.0
                        else:
                            w = math.sqrt(1 - (self.goal_list[self.goal_id-1][2]) ** 2)
                            self.pose_stamped.pose.orientation.z = self.goal_list[self.goal_id-1][2]
                            self.pose_stamped.pose.orientation.w = w 
                        self.nav_goal_pub.publish(self.pose_stamped) 
                        self.nav_working = 1
                        pub_str = "start_nav_%d" % self.goal_id
                        self.voice_cmd_fb_pub.publish(pub_str)
                        rospy.loginfo('Start Nav to Goal %d',self.goal_id)                     
                    else:
                        self.voice_cmd_fb_pub.publish('no_goal') 
                        rospy.loginfo('Goal %d not set,Faild',self.goal_id)
                        self.goal_id = 0
            else:
                pass

                # rospy.loginfo('Test')  
            self.rate.sleep()            

    def voice_cmd_callback(self,data):
        if self.cmd_vel_sub_number > 0:
            if data.data == 'forword':
                self.voice_cmd_fb_pub.publish(data.data)
                self.twist.linear.x = self.line_speed_x
                self.last_move_cmd_time = rospy.Time.now()
            elif data.data == 'backword':
                self.voice_cmd_fb_pub.publish(data.data)
                self.twist.linear.x = self.line_speed_x*-1.0
                self.last_move_cmd_time = rospy.Time.now()
            elif data.data == 'left':
                self.voice_cmd_fb_pub.publish(data.data)
                self.twist.angular.z = self.angle_speed_z
                self.last_move_cmd_time = rospy.Time.now()
            elif data.data == 'right':
                self.twist.angular.z = self.angle_speed_z*-1.0
                self.voice_cmd_fb_pub.publish(data.data)
                self.last_move_cmd_time = rospy.Time.now()
            elif data.data == 'stop':
                self.voice_cmd_fb_pub.publish(data.data)
                self.twist.linear.x = 0.0
                self.twist.angular.z = 0.0
                self.last_move_cmd_time = rospy.Time.now()
            elif data.data == 'speed_up':
                if self.line_speed_x < 0.5:
                    self.line_speed_x += 0.1
                    self.voice_cmd_fb_pub.publish(data.data) 
                else:
                    self.voice_cmd_fb_pub.publish('speed_max')
                self.last_move_cmd_time = rospy.Time.now()    
            elif data.data == 'speed_down':
                if self.line_speed_x > 0.1:
                    self.line_speed_x -= 0.1
                    self.voice_cmd_fb_pub.publish(data.data) 
                else:
                    self.voice_cmd_fb_pub.publish('speed_min')
                self.last_move_cmd_time = rospy.Time.now()    
            elif data.data == 'turn_up':
                if self.angle_speed_z < 1.0:
                    self.angle_speed_z += 0.1 
                    self.voice_cmd_fb_pub.publish(data.data)  
                else:
                    self.voice_cmd_fb_pub.publish('turn_max')                
            elif data.data == 'turn_down':
                if self.angle_speed_z > 0.1:
                    self.angle_speed_z -= 0.1  
                    self.voice_cmd_fb_pub.publish(data.data)   
                else:
                    self.voice_cmd_fb_pub.publish('turn_min')
                self.last_move_cmd_time = rospy.Time.now()    
        else:
            self.voice_cmd_fb_pub.publish('base_not_ready')
            
        if data.data == 'goal_1':
            self.goal_id = 1
            self.nav_working = 0
        elif data.data == 'goal_2':
            self.goal_id = 2  
            self.nav_working = 0
        elif data.data == 'goal_3':
            self.goal_id = 3    
            self.nav_working = 0   
        elif data.data == 'goal_cancel':
            cancel = GoalID()
            cancel.stamp = rospy.Time.now()
            cancel.id = '1'
            self.nav_cancel_pub.publish(cancel)
            self.nav_working = 0
            self.goal_id = 0 
            self.voice_cmd_fb_pub.publish('goal_cancel')                                 
        else:
            pass

    def nav_status_callback(self, data):
        if self.nav_working != 0:
            if data.status.status == 3 : # goal reached
                pub_str = "goal_reached_%d" % self.goal_id
                self.voice_cmd_fb_pub.publish(pub_str)
                self.nav_working = 0
                self.goal_id = 0
            else:
                self.voice_cmd_fb_pub.publish('nav_faild')
                self.nav_working = 0
                self.goal_id = 0            
        
#main function
if __name__=="__main__":
    try:
        rospy.init_node('artificial_idiot_node',anonymous=False)
        va = ArtificialIdiot()
        rospy.spin()
    except KeyboardInterrupt:    
        rospy.loginfo("Shutting down")
