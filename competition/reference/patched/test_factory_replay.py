#!/usr/bin/env python3
"""Factory callback regression: captured JPEGs and exact synthetic centroids.

ROS constructors/publishers are mocked; no ROS master or devices are used.
"""
import ast
import copy
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
import factory_auto_run as factory
from deepbot_auto_driver.msg import DriverMode

STAGE = Path(__file__).resolve().parent


class Recorder:
    def __init__(self, *args, **kwargs):
        self.rows = []

    def publish(self, msg):
        self.rows.append(copy.deepcopy(msg))


def make_follower():
    with patch.object(factory.rospy, 'get_param', side_effect=lambda name, default: default), \
            patch.object(factory.rospy, 'Publisher', Recorder), \
            patch.object(factory.rospy, 'Subscriber'), \
            patch.object(factory.rospy, 'Timer'), \
            patch.object(factory.rospy, 'on_shutdown'):
        obj = factory.Follower()
    msg = DriverMode(mask_x_left=.5, mask_x_right=1., mask_y_top=.6,
                     mask_y_bot=.85, center_target=.8, vel_x=.2,
                     vel_z_P=.012, vel_z_D=.005, en=4)
    obj.driver_mode_callback(msg)
    return obj, msg


def check(label, condition, detail=''):
    print(label, 'PASS' if condition else 'FAIL', detail, flush=True)
    if not condition:
        raise AssertionError(label)


# Execute the actual original callback for an independent centroid comparison.
original = STAGE / 'factory_auto_run_original.py'
tree = ast.parse(original.read_text())
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Follower')
callback = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'image_callback')
scope = {'cv2': cv2}
exec(compile(ast.fix_missing_locations(ast.Module(body=[callback], type_ignores=[])),
             str(original), 'exec'), scope)
count = 0
for run in ('20261006_151837', '20261006_161059', '20261006_161714'):
    files = sorted((STAGE / 'runs' / run).glob('frame_*.jpg'))
    check('REPLAY_BANK_' + run, len(files) == 13, str(len(files)))
    obj, _ = make_follower()
    for file in files:
        frame = cv2.imread(str(file))
        baseline, _ = make_follower()
        baseline.state_last = 4
        baseline.bridge.imgmsg_to_cv2 = lambda msg, **kwargs: frame.copy()
        with patch.object(cv2, 'imshow'), patch.object(cv2, 'waitKey'):
            scope['image_callback'](baseline, None)
        raw = baseline.cmd_vel_pub.rows[-1]
        obj.process_image(frame)
        actual = obj.cmd_vel_pub.rows[-1]
        expected_error = -raw.angular.z / (.012 + .005)
        check('FACTORY_CENTROID_' + file.parent.name + '_' + file.stem,
              raw.linear.x > 0 and actual.linear.x > 0
              and abs(obj.last_erro - expected_error) < 1e-6
              and 0 <= actual.linear.x <= .025 and abs(actual.angular.z) <= .08)
        count += 1

# Yellow pixels with exact centroid in the original 320x240 ROI.
def yellow_at(cx):
    hsv = np.zeros((240, 320, 3), dtype=np.uint8)
    hsv[170:181, cx-5:cx+6] = (30, 150, 230)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

obj, mode = make_follower()
mode.vel_z_P, mode.vel_z_D = .002, .001
obj.driver_mode_callback(mode)
obj.process_image(yellow_at(266))  # error +10, first D=0
first = obj.cmd_vel_pub.rows[-1].angular.z
obj.process_image(yellow_at(261))  # error +5, D=-5
second = obj.cmd_vel_pub.rows[-1].angular.z
obj.process_image(yellow_at(261))  # stationary error, D=0
third = obj.cmd_vel_pub.rows[-1].angular.z
check('DERIVATIVE_HISTORY', abs(first + .020) < 1e-8 and abs(second + .005) < 1e-8
      and abs(third + .010) < 1e-8 and obj.last_erro == 5,
      repr((first, second, third)))
obj.process_image(yellow_at(246))
check('STEERING_SIGN', first < 0 and obj.twist.angular.z > 0)
obj.process_image(np.zeros((240, 320, 3), dtype=np.uint8))
check('BLANK_STOP', obj.twist.linear.x == 0 and obj.twist.angular.z == 0)
obj.process_image(yellow_at(266))
check('RESUME_WITHOUT_D_KICK', abs(obj.twist.angular.z + .020) < 1e-8)
mode.center_target = float('nan')
obj.driver_mode_callback(mode)
obj.process_image(yellow_at(266))
check('INVALID_MODE_STOP', obj.state == 0 and obj.twist.linear.x == 0 and obj.twist.angular.z == 0)
mode.center_target, mode.en = .8, 0
obj.driver_mode_callback(mode)
obj.process_image(yellow_at(266))
check('DISABLED_STOP', obj.twist.linear.x == 0 and obj.twist.angular.z == 0)
print('FACTORY_REPLAY_PASS frames=%d NO_ROS_NO_DEVICES' % count, flush=True)
