"""ROS 1 subscriber adapter. No publishers, roscore, device nodes or driver launch."""
import io
import os
import time
import xmlrpc.client

from .core import SessionWriter, dumps
from .callback_gate import CallbackGate


class MasterTimeout(xmlrpc.client.Transport):
    def make_connection(self, host):
        connection = super().make_connection(host)
        connection.timeout = 3
        return connection


def check_master(uri):
    if not uri or not uri.startswith('http://'):
        raise ValueError('explicit ROS_MASTER_URI=http://... required; recorder never starts a master')
    try:
        with xmlrpc.client.ServerProxy(uri, transport=MasterTimeout()) as master:
            code, message, _ = master.getPid('/deepbot_passive_data_preflight')
        if code != 1:
            raise RuntimeError('master rejected preflight: ' + str(message))
    except (OSError, xmlrpc.client.Error) as exc:
        raise RuntimeError('existing ROS master unavailable; no hardware or master was started') from exc


def capture(root, session_id, config, seconds):
    # Lazy imports let offline CLI work on a host without ROS.
    try:
        import rospy
        from sensor_msgs.msg import CompressedImage, Image
        from nav_msgs.msg import Odometry
        from geometry_msgs.msg import Twist
    except ImportError as exc:
        raise RuntimeError('ROS 1 Python dependencies unavailable; no session started') from exc
    if config['role'] == 'synthetic':
        raise ValueError('ROS capture requires an explicitly non-synthetic role')
    check_master(os.environ.get('ROS_MASTER_URI'))
    rospy.init_node('deepbot_passive_data_recorder', anonymous=True, disable_signals=True)
    configured_streams = list(config['cameras'].values()) + [config[name] for name in ('feedback', 'command') if config.get(name)]
    resolved_topics = [rospy.resolve_name(s['topic']) for s in configured_streams]
    if len(set(resolved_topics)) != len(resolved_topics):
        raise ValueError('ROS remapping resolved distinct streams to the same topic')
    for spec, resolved in zip(configured_streams, resolved_topics):
        spec['requested_topic'] = spec['topic']
        spec['topic'] = resolved
    writer = SessionWriter(root, session_id, config)
    subscribers, failures = [], []
    gate = CallbackGate()
    ready_once = False
    reason = 'duration_elapsed'
    types = {'sensor_msgs/CompressedImage': CompressedImage, 'sensor_msgs/Image': Image,
             'nav_msgs/Odometry': Odometry, 'geometry_msgs/Twist': Twist}

    def receive(msg, stream, spec):
        receipt_mono, receipt_unix = time.monotonic_ns(), time.time_ns()
        try:
            serialized = io.BytesIO()
            msg.serialize(serialized)
            original = serialized.getvalue()
            header = getattr(msg, 'header', None)
            stamp = header.stamp.to_nsec() if header is not None else None
            descriptor, motion = None, None
            metadata = dict(ros_type=msg._type, ros_md5=msg._md5sum,
                ros_definition=msg._full_text,
                header_frame_id=getattr(header, 'frame_id', None),
                header_seq=getattr(header, 'seq', None),
                original_format=getattr(msg, 'format', None),
                publisher_callerid=(getattr(msg, '_connection_header', None) or {}).get('callerid'))
            if stream in ('high', 'low'):
                data = bytes(msg.data)
                if isinstance(msg, CompressedImage):
                    descriptor = dict(format='compressed')  # Actual codec detected from bytes; empty format is legal.
                else:
                    descriptor = dict(format='raw', width=msg.width, height=msg.height,
                                      step=msg.step, encoding=msg.encoding, is_bigendian=msg.is_bigendian)
            else:
                data = original
                twist = msg.twist.twist if isinstance(msg, Odometry) else msg
                motion = dict(vx_mps=twist.linear.x, vy_mps=twist.linear.y, wz_radps=twist.angular.z)
            record = writer.append(stream, data, descriptor=descriptor, motion=motion,
                source_stamp_ns=stamp, receipt_mono_ns=receipt_mono, receipt_unix_ns=receipt_unix,
                source_now_ns=rospy.Time.now().to_nsec() if spec.get('compare_source_to_ros_time') is True else None,
                serialized_message=original, message_metadata=metadata)
            if not record['valid']:
                failures.append('%s: %s' % (stream, ','.join(record['diagnostics'])))
        except Exception as exc:
            failures.append('callback_error: ' + repr(exc))

    try:
        for stream, spec in list(config['cameras'].items()) + [
                (name, config[name]) for name in ('feedback', 'command') if config.get(name)]:
            subscribers.append(rospy.Subscriber(spec['topic'], types[spec['message_type']],
                lambda msg, s=stream, cfg=spec: gate.run(receive, msg, s, cfg),
                queue_size=30, buff_size=16 * 1024 * 1024))
        print('SESSION=' + str(writer.path), flush=True)
        next_status = 0
        while True:
            writer.drain_requests()
            # Sample frame age under the writer lock: callbacks may update the
            # latest receipt while this loop is waiting to acquire that lock.
            status = writer.status()
            now = time.monotonic_ns()
            ready_once = ready_once or status['ready']
            if now >= next_status:
                print(dumps(status), flush=True)
                next_status = now + 1_000_000_000
            if failures:
                reason = 'callback_or_data_error'
                break
            if rospy.is_shutdown():
                failures.append('ROS_shutdown_before_operator_stop')
                reason = 'ROS_shutdown'
                break
            if status['free_bytes'] < config['reserve_bytes']:
                failures.append('low_disk')
                reason = 'low_disk'
                break
            if (writer.path / 'STOP_RECORDING').exists():
                reason = 'operator_stop'
                break
            if now - writer.start_ns > config['startup_grace_ns'] and not status['ready']:
                failures.append('required_stream_missing_or_stale')
                reason = 'required_stream_missing_or_stale'
                break
            if now - writer.start_ns >= seconds * 1_000_000_000:
                break
            time.sleep(0.05)
    except KeyboardInterrupt:
        reason = 'operator_interrupt'
    except BaseException as exc:
        failures.append(repr(exc))
        reason = 'capture_exception'
    finally:
        gate.close_intake()
        for sub in subscribers:
            try:
                sub.unregister()
            except Exception as exc:
                failures.append('unsubscribe_error: ' + repr(exc))
        gate.drain()  # Includes admitted callbacks still waiting for the writer lock.
        try:
            writer.drain_requests()
        except Exception as exc:
            failures.append('event_drain_error: ' + repr(exc))
        if not ready_once:
            failures.append('never_ready')
        writer.manifest['errors'].extend(failures)
        writer.manifest['admitted_callbacks'] = gate.admitted
        writer.manifest['capture_boundary'] = 'callback_gate_admission; admitted callbacks drained before close'
        writer.close(reason, complete=not failures)
        print('CLOSED=' + dumps(dict(path=str(writer.path), complete=writer.manifest['complete'],
                                    reason=writer.manifest['close_reason'], errors=failures)), flush=True)
        print('Recorder exit does not stop the vehicle.', flush=True)
        rospy.signal_shutdown('passive recorder closed')
    return 0 if writer.manifest['complete'] else 2
