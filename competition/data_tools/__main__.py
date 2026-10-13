"""Passive capture CLI: start, stop, event, export, inspect. Never launches hardware."""
import argparse
from pathlib import Path
import sys
import time
import uuid

from .core import atomic_json, dumps, load_json, validate_config, write_new
from .offline import export_session, inspect_export, inspect_session


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    start = commands.add_parser('start')
    start.add_argument('--backend', choices=('synthetic', 'ros'), required=True)
    start.add_argument('--config', type=Path, required=True)
    start.add_argument('--root', type=Path, required=True)
    start.add_argument('--session', required=True)
    start.add_argument('--seconds', type=float, default=20)
    stop = commands.add_parser('stop')
    stop.add_argument('--session', type=Path, required=True)
    event = commands.add_parser('event')
    event.add_argument('--session', type=Path, required=True)
    event.add_argument('--type', required=True)
    event.add_argument('--phase', choices=('point', 'start', 'end'), default='point')
    event.add_argument('--interval-id')
    event.add_argument('--reason', default='')
    export = commands.add_parser('export')
    export.add_argument('--session', type=Path, required=True)
    export.add_argument('--output', type=Path, required=True)
    inspect = commands.add_parser('inspect')
    inspect.add_argument('--session', type=Path)
    inspect.add_argument('--export', dest='export_path', type=Path)
    inspect.add_argument('--report', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == 'start':
            if not 0.1 <= args.seconds <= 1800:
                raise ValueError('seconds must be 0.1..1800')
            config = validate_config(load_json(args.config))
            if args.backend == 'ros':
                from .ros_capture import capture
            else:
                from .synthetic import capture
            return capture(args.root, args.session, config, args.seconds)
        if args.action in ('stop', 'event'):
            root = args.session.resolve()
            manifest = load_json(root / 'manifest.json')
            if manifest.get('state') != 'recording' or manifest.get('complete'):
                raise ValueError('session is not recording; do not alter closed data')
            if args.action == 'stop':
                write_new(root / 'STOP_RECORDING', b'operator_request\n')
                print('STOP_REQUESTED; wait for CLOSED and inspect manifest; this does not stop motion')
            else:
                if args.phase != 'point' and not args.interval_id:
                    raise ValueError('--interval-id required for interval start/end')
                value = dict(event_type=args.type, phase=args.phase, interval_id=args.interval_id,
                             reason=args.reason, requested_unix_ns=time.time_ns())
                request = uuid.uuid4().hex
                atomic_json(root / 'requests' / (request + '.json'), value)
                print('EVENT_REQUESTED=' + request + '; event time is recorder receipt; check events.jsonl acknowledgement')
            return 0
        if args.action == 'export':
            report = export_session(args.session, args.output)
            print(dumps(report))
            return 0 if report['quality_ok'] else 2
        if bool(args.session) == bool(args.export_path):
            raise ValueError('inspect requires exactly one of --session or --export')
        report = inspect_export(args.export_path) if args.export_path else inspect_session(args.session)[0]
        if args.report:
            write_new(args.report, (dumps(report) + '\n').encode('utf-8'))
        print(dumps(report))
        quality_ok = report.get('quality_ok', report.get('quality', {}).get('quality_ok', False))
        return 0 if report['integrity_ok'] and quality_ok else 2
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print('DATA_TOOL_ERROR: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
