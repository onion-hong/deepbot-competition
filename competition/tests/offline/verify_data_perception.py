"""Synthetic B-to-C integration acceptance. No ROS, devices, or motion output."""
import argparse
import io
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT))

from PIL import Image
from competition.data_tools.core import SessionWriter, load_json
from competition.data_tools.offline import export_session, inspect_export
from competition.perception.synthetic import scene
from competition.perception.replay import replay
from competition.interfaces.validate import loads, validate_stream


def run(root):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    config = load_json(PROJECT / 'competition/data_tools/synthetic.example.json')
    writer = SessionWriter(root, 'synthetic_pipeline', config,
                           clock_id='synthetic-fixture-clock')
    for index, name in enumerate(('straight', 'left_curve', 'no_line')):
        for camera in ('high', 'low'):
            buffer = io.BytesIO()
            Image.fromarray(scene(name)).save(buffer, format='PNG')
            # Explicit fixture timestamps: never label these as measured cadence.
            stamp = 1_000_000_000 + index * 100_000_000
            stamp += 1_000_000 if camera == 'low' else 0
            writer.append(camera, buffer.getvalue(), descriptor={'format': 'compressed'},
                          source_stamp_ns=stamp, receipt_mono_ns=stamp,
                          receipt_unix_ns=stamp)
    writer.close('synthetic_pipeline_complete')
    quality = export_session(writer.path, root / 'export')
    assert quality['quality_ok'], quality
    assert quality['public_frame_count'] == 6, quality
    assert all(item['demonstration_samples'] == 0 for item in quality['cameras'].values())
    assert inspect_export(root / 'export')['integrity_ok']
    result = replay(root / 'export', root / 'replay',
                    manifest=root / 'export/camera_frames.jsonl', dataset_role='synthetic')
    rows = [loads(line) for line in
            (root / 'replay/records.jsonl').read_text(encoding='utf-8').splitlines()]
    count = validate_stream(rows)
    roads = [record for record in rows if record['kind'] == 'road']
    assert result['processed'] == 6 and result['rejected'] == 0, result
    assert [row['payload']['valid'] for row in roads] == [True, True, True, True, False, False]
    assert count == 12
    summary = dict(status='PASS', scope='synthetic storage/export/perception/contract only',
                   frames=6, contract_records=count, valid_roads=4, invalid_roads=2,
                   demonstration_samples=0, autonomous_success=None,
                   receipt_clock='explicit synthetic fixture, not measured capture cadence')
    (root / 'ROOT_ACCEPTANCE.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='new output directory')
    args = parser.parse_args()
    print(json.dumps(run(args.output), ensure_ascii=False))
