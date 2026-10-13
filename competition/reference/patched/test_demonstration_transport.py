#!/usr/bin/env python3
"""Isolated synthetic ROS transport test. Never starts camera/base/controllers."""
import json
import os
import pty
import select
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time
import tty

import cv2
import numpy as np
import rospy
from nav_msgs.msg import Odometry
from sensor_msgs.msg import CompressedImage
from export_demonstration import export


def stop(process):
    if process.poll() is None:
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait(timeout=5)


def main():
    port = 11312
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1', port)) == 0:
            raise RuntimeError('test master port already occupied; refusing to reuse')
    env = os.environ.copy()
    env['ROS_MASTER_URI'] = 'http://127.0.0.1:%d' % port
    env['ROS_IP'] = '127.0.0.1'
    env.pop('ROS_HOSTNAME', None)
    os.environ.update(env)
    os.environ.pop('ROS_HOSTNAME', None)
    stage = Path(__file__).resolve().parent
    processes = []
    with tempfile.TemporaryDirectory(prefix='synthetic_transport_') as directory:
        root = Path(directory)
        config = root / 'fixture.json'
        config.write_text(json.dumps({'synthetic': True, 'hardware': False}))
        with (root / 'core.log').open('w') as core_log:
            core = subprocess.Popen(['roscore', '-p', str(port)], env=env, stdout=core_log,
                                    stderr=subprocess.STDOUT)
            processes.append(core)
            try:
                deadline = time.monotonic()+10
                while time.monotonic() < deadline:
                    with socket.socket() as sock:
                        if sock.connect_ex(('127.0.0.1', port)) == 0:
                            break
                    if core.poll() is not None:
                        raise RuntimeError('test roscore failed')
                    time.sleep(.1)
                else:
                    raise RuntimeError('test roscore timeout')
                rospy.init_node('synthetic_recording_source', anonymous=True, disable_signals=True)
                image_pub = rospy.Publisher('/recording_fixture/image', CompressedImage, queue_size=10)
                odom_pub = rospy.Publisher('/recording_fixture/odom', Odometry, queue_size=30)
                rng = np.random.RandomState(42)
                _, jpeg = cv2.imencode('.jpg', rng.randint(0, 256, (720, 1280, 3), dtype=np.uint8))
                recorder_log = (root / 'recorder.log').open('w')
                command = ['python3', str(stage/'record_demonstration.py'), '--root', str(root/'data'),
                           '--split', 'development', '--route-id', 'SYNTHETIC_ONLY',
                           '--camera-pose', 'synthetic', '--operator', 'synthetic_fixture',
                           '--config', str(config), '--image-topic', '/recording_fixture/image',
                           '--odom-topic', '/recording_fixture/odom', '--max-seconds', '30']
                recorder = subprocess.Popen(command, env=env, stdout=recorder_log, stderr=subprocess.STDOUT)
                processes.append(recorder)
                deadline = time.monotonic()+8
                while image_pub.get_num_connections() == 0 or odom_pub.get_num_connections() == 0:
                    if time.monotonic() > deadline or recorder.poll() is not None:
                        raise RuntimeError('synthetic subscribers not ready')
                    time.sleep(.05)
                start = time.monotonic(); next_image = start
                images_sent = odom_sent = 0
                while time.monotonic()-start < 3:
                    od = Odometry(); od.header.stamp = rospy.Time.now()
                    od.twist.twist.linear.x = .04; od.twist.twist.angular.z = .1
                    odom_pub.publish(od); odom_sent += 1
                    now = time.monotonic()
                    if now >= next_image:
                        im = CompressedImage(); im.header.stamp = rospy.Time.now()
                        im.format = 'jpeg'; im.data = jpeg.tobytes()
                        image_pub.publish(im); images_sent += 1; next_image = now+1/30
                    time.sleep(.01)
                time.sleep(.2)
                sessions = list((root/'data').iterdir()); assert len(sessions) == 1
                session = sessions[0]
                (session/'STOP_RECORDING').touch()
                assert recorder.wait(timeout=5) == 0
                recorder_log.close()
                manifest = json.loads((session/'manifest.json').read_text())
                assert manifest['complete'] and manifest['close_reason'] == 'operator_stop_file', manifest
                assert manifest['counts']['/recording_fixture/image'] == images_sent, (manifest, images_sent)
                assert manifest['counts']['/recording_fixture/odom'] == odom_sent, (manifest, odom_sent)
                stats = export(session)
                assert stats['pair_fraction'] >= .95 and stats['paired'] >= 20, stats
                print('TRANSPORT_PASS images=%d odom=%d paired=%d fraction=%.3f max_skew=%.4f'
                      % (images_sent, odom_sent, stats['paired'], stats['pair_fraction'], stats['max_skew_s']))
                # Verify existing protected driver can receive manual telemetry without
                # injecting velocity while no command has ever been received.
                master_fd, slave_fd = pty.openpty()
                tty.setraw(slave_fd)  # Disable terminal echo before injecting binary packets.
                slave_path = os.ttyname(slave_fd)
                assert slave_path.startswith('/dev/pts/')
                idle_log = (root/'idle_driver.log').open('w')
                idle = subprocess.Popen([
                    '/home/deepbot/catkin_ws/devel/lib/deepbot_driver/deepbot_driver',
                    '__name:=driver_receive_only_fixture', '_port_name:='+slave_path,
                    '_odom_topic:=/recording_fixture/idle_odom',
                    'cmd_vel:=/recording_fixture/unused_cmd',
                    'servo:=/recording_fixture/unused_servo'], env=env,
                    stdout=idle_log, stderr=subprocess.STDOUT)
                processes.append(idle)
                samples = []
                idle_sub = rospy.Subscriber('/recording_fixture/idle_odom', Odometry,
                                             lambda msg: samples.append(msg))
                try:
                    received_bytes = bytearray()
                    start = time.monotonic()
                    packet = bytearray(32); packet[:4] = bytes([0xAB,0xCD,32,0x10])
                    packet[16:18] = (40).to_bytes(2,'big',signed=True)
                    packet[20:22] = (100).to_bytes(2,'big',signed=True)
                    packet[-1] = sum(packet[:-1]) % 256
                    while time.monotonic()-start < 2:
                        os.write(master_fd, packet)
                        ready, _, _ = select.select([master_fd], [], [], .04)
                        if ready:
                            received_bytes.extend(os.read(master_fd,4096))
                    assert samples and idle.poll() is None, len(samples)
                    assert not received_bytes, (len(received_bytes), received_bytes[:32].hex())
                    actual_v = samples[-1].twist.twist.linear.x
                    actual_w = samples[-1].twist.twist.angular.z
                    # Firmware/driver velocity storage is float32; compare well below
                    # the 0.001 wire quantization, not at double-only precision.
                    assert abs(actual_v-.04)<1e-6, actual_v
                    assert abs(actual_w-.1)<1e-6, actual_w
                    print('IDLE_DRIVER_PASS odom_samples=%d serial_tx_bytes=0; existing watchdog unchanged' % len(samples))
                finally:
                    idle_sub.unregister(); stop(idle)
                    idle_log.close(); os.close(slave_fd); os.close(master_fd)
                # A separate capture with no source must fail rather than claim readiness.
                missing_log = (root/'missing.log').open('w')
                command[command.index('--root')+1] = str(root/'missing_data')
                missing = subprocess.Popen(command, env=env, stdout=missing_log, stderr=subprocess.STDOUT)
                processes.append(missing)
                assert missing.wait(timeout=10) == 1
                missing_log.close()
                missing_session = next((root/'missing_data').iterdir())
                missing_manifest = json.loads((missing_session/'manifest.json').read_text())
                assert not missing_manifest['complete']
                assert missing_manifest['close_reason'] == 'required_stream_missing_or_stale'
                print('MISSING_STREAM_PASS incomplete session; no hardware nodes started')
            finally:
                for process in reversed(processes):
                    stop(process)
                if not rospy.is_shutdown():
                    rospy.signal_shutdown('synthetic test complete')


if __name__ == '__main__':
    main()
