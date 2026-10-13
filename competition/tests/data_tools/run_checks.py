"""Run only B's hardware-free tests and retain evidence in a fresh directory."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
import uuid


def main():
    here = Path(__file__).resolve().parent
    repo = here.parents[2]
    sys.path.insert(0, str(repo))
    output = here / 'outputs' / ('check_' + uuid.uuid4().hex)
    output.mkdir(parents=True, exist_ok=False)
    suite = unittest.defaultTestLoader.discover(str(here), pattern='test_*.py')
    with (output / 'tests.txt').open('x', encoding='utf-8') as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    report = dict(python=sys.executable, version=sys.version, test_count=result.testsRun,
        failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
        success=result.wasSuccessful(), ros_transport_executed=False, hardware_access=False,
        test_data_root=str(sys.modules['test_data_tools'].RUN),
        dependencies={name: importlib.util.find_spec(name) is not None for name in ('PIL', 'rospy', 'rosbag')},
        source_sha256={p.relative_to(repo).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                       for folder in (repo / 'competition/data_tools', here)
                       for p in folder.glob('*.py')})
    (output / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print((output / 'tests.txt').read_text(encoding='utf-8'))
    print('TEST_EVIDENCE=' + str(output))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
