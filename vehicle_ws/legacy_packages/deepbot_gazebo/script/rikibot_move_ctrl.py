#!/usr/bin/env python
# _*_ coding:utf-8 _*_

import rospy
from geometry_msgs.msg import Twist


class RikibotMove():
    def __init__(self):
        rospy.init_node('rikibot_move_node', log_level=rospy.INFO)
        r = rospy.Rate(10)
        rospy.on_shutdown(self.shutdown)

        self.vel_pub = rospy.Publisher('/cmd_vel', Twist, queue_size=5)

        twist = Twist()
        while not rospy.is_shutdown():
            twist.linear.x = 0.2
            #twist.linear.y = 0
            twist.angular.z =0.1
            rospy.loginfo("linear x: %f, linear y : %f, angular z: %f", twist.linear.x, twist.linear.y, twist.angular.z)
            self.vel_pub.publish(twist)
            r.sleep()



    def shutdown(self):
        # Release handle to the webcam
        rospy.logwarn("now will shutdown move robot node ...")

if __name__ == '__main__':
    try:
        ctrl = RikibotMove()
        rospy.spin()
    except Exception, e:
        rospy.logerr("%s", str(e))
        os._exit(1)

