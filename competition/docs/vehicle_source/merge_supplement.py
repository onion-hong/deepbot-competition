"""Merge the one-shot source supplement locally; no remote access or source execution."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / 'competition/docs/vehicle_source'
SUPPLEMENT = ROOT / 'vehicle_snapshot_20261013_source_supplement'


def main():
    workspace = ROOT / 'vehicle_ws'
    old = (workspace / 'reference').resolve()
    new = (workspace / 'legacy_packages').resolve()
    assert workspace.resolve() in old.parents and workspace.resolve() in new.parents
    if old.exists():
        if new.exists():
            raise FileExistsError(new)
        old.rename(new)
    inventory = json.loads((DOCS / 'SOURCE_INVENTORY.json').read_text(encoding='utf-8'))
    for row in inventory:
        if row['destination']:
            row['destination'] = row['destination'].replace('vehicle_ws/reference/', 'vehicle_ws/legacy_packages/')
    packages = json.loads((DOCS / 'PACKAGES.json').read_text(encoding='utf-8'))
    for row in json.loads((SUPPLEMENT / 'FILE_MANIFEST.json').read_text(encoding='utf-8')):
        if not row['copy']:
            continue
        rel = row['relative_path']
        if '/results/' in rel or rel.endswith(('/race.xml', '/traffic.xml')):
            inventory.append({'source': 'source/' + rel, 'snapshot': SUPPLEMENT.name,
                              'source_sha256': row['sha256'], 'source_bytes': row['bytes'],
                              'destination': None, 'package': None, 'decision': 'excluded',
                              'reason': 'generated result or model asset retained only in private snapshot'})
            continue
        choices = [(name, data) for name, data in packages.items()
                   if rel.startswith(data['source_root'].split('/catkin_ws/src/', 1)[1] + '/')]
        name, info = max(choices, key=lambda pair: len(pair[1]['source_root']))
        subpath = rel[len(info['source_root'].split('/catkin_ws/src/', 1)[1])+1:]
        core = info['category'] == 'core'
        if name == 'deepbot' and not subpath.startswith(('include/', 'src/')):
            core = False
        category = 'src' if core else 'legacy_packages'
        path = workspace / category / name / subpath
        data = (SUPPLEMENT / 'source' / rel).read_bytes()
        assert hashlib.sha256(data).hexdigest() == row['sha256']
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            assert path.read_bytes() == data, str(path)
        else:
            with path.open('xb') as out:
                out.write(data)
        inventory.append({'source': 'source/' + rel, 'snapshot': SUPPLEMENT.name,
                          'source_sha256': row['sha256'], 'source_bytes': row['bytes'],
                          'destination': path.relative_to(ROOT).as_posix(), 'package': name,
                          'decision': category, 'reason': 'source/resource supplement from same 23 package roots'})
    (DOCS / 'SOURCE_INVENTORY.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (DOCS / 'SUPPLEMENT_INVENTORY.json').write_bytes((SUPPLEMENT / 'FILE_MANIFEST.json').read_bytes())
    print('Supplement copied:', sum(x.get('snapshot') == SUPPLEMENT.name for x in inventory))


if __name__ == '__main__':
    main()
