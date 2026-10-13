"""Static closure and provenance audit. Never imports/executes vehicle code.

Writes only reports beneath competition/docs/vehicle_source. This is NOT catkin.
"""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / 'competition/docs/vehicle_source'
WS = ROOT / 'vehicle_ws'


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    failures = []
    packages = {}
    for path in sorted((WS / 'src').rglob('package.xml')):
        tree = ET.parse(path).getroot()
        name = tree.findtext('name')
        if name in packages:
            failures.append('duplicate active package: ' + name)
        packages[name] = path.parent
        if not (path.parent / 'CMakeLists.txt').is_file():
            failures.append('missing CMake: ' + name)
        if not tree.findtext('maintainer', '').strip():
            failures.append('empty maintainer: ' + name)
    assert (WS / 'legacy_packages/CATKIN_IGNORE').is_file()
    source_rows = json.loads((DOCS / 'SOURCE_INVENTORY.json').read_text(encoding='utf-8'))
    patches = []
    mapped = set()
    changed = []
    snapshots_available = True
    for row in source_rows:
        destination = row['destination']
        if not destination:
            continue
        target = ROOT / destination
        original = ROOT / row.get('snapshot', 'vehicle_snapshot_20261013_readonly') / row['source']
        mapped.add(destination)
        actual_hash = digest(target)
        if not original.is_file():
            snapshots_available = False
            if actual_hash != row.get('destination_sha256'):
                failures.append('workspace differs from published manifest: ' + destination)
            if row.get('modified'):
                changed.append(destination)
            continue
        if digest(original) != row['source_sha256']:
            failures.append('source snapshot hash changed: ' + row['source'])
        row['destination_sha256'] = actual_hash
        row['modified'] = row['destination_sha256'] != row['source_sha256']
        if row['modified']:
            changed.append(destination)
            try:
                patches.extend(difflib.unified_diff(original.read_text(encoding='utf-8-sig').splitlines(True),
                                                   target.read_text(encoding='utf-8-sig').splitlines(True),
                                                   fromfile='snapshot/' + row['source'], tofile=destination))
            except UnicodeError:
                failures.append('unexpected changed binary: ' + destination)
    (DOCS / 'SOURCE_INVENTORY.json').write_text(json.dumps(source_rows, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    if snapshots_available:
        (DOCS / 'CHANGES.patch').write_text(''.join(patches), encoding='utf-8', newline='\n')
    references = []
    external = set()
    build_missing = []
    for name, root in packages.items():
        cmake = re.sub(r'#.*', '', (root / 'CMakeLists.txt').read_text(encoding='utf-8'))
        # Static file operands only; dependency resolution requires real Noetic.
        for command, body in re.findall(r'(add_library|add_executable|add_message_files|add_service_files|generate_dynamic_reconfigure_options)\s*\((.*?)\)', cmake, re.S):
            words = body.split()
            folder = 'msg' if command == 'add_message_files' else 'srv' if command == 'add_service_files' else ''
            if 'DIRECTORY' in words:
                folder = words[words.index('DIRECTORY') + 1]
            for word in words:
                if '$' in word or not re.search(r'\.(?:cpp|cc|c|h|hpp|msg|srv|cfg)$', word):
                    continue
                p = root / folder / word
                if not p.is_file():
                    build_missing.append(name + ':' + str(p.relative_to(root)))
        for p in root.rglob('*'):
            if not p.is_file():
                continue
            if p.suffix in {'.launch', '.urdf', '.xacro', '.xml', '.test'}:
                try:
                    ET.parse(p)
                except ET.ParseError as error:
                    # Captured pluginlib manifests may consist of sibling library
                    # elements. Check fragment syntax, not a guessed runtime schema.
                    if p.name == 'nodelet_plugins.xml':
                        try:
                            fragment = ET.fromstring('<audit_root>' + p.read_text(encoding='utf-8') + '</audit_root>')
                            assert all(child.tag == 'library' for child in fragment)
                        except (ET.ParseError, AssertionError):
                            failures.append(str(p.relative_to(ROOT)) + ': XML fragment ' + str(error))
                    else:
                        failures.append(str(p.relative_to(ROOT)) + ': XML ' + str(error))
            if p.suffix == '.py':
                try:
                    ast.parse(p.read_text(encoding='utf-8-sig'))
                except SyntaxError as error:
                    failures.append(str(p.relative_to(ROOT)) + ': Python parse ' + str(error))
            if p.suffix not in {'.launch', '.urdf', '.xacro', '.xml'}:
                continue
            text = p.read_text(encoding='utf-8-sig')
            # XML comments are not active resource references.
            text = re.sub(r'<!--.*?-->', '', text, flags=re.S)
            for pkg, path in re.findall(r'\$\(find\s+([^\s)]+)\)/([^\s"<>]+)', text):
                state = 'external_dependency'
                if '$' in path:
                    state = 'dynamic_reference_not_resolved'
                elif pkg in packages:
                    state = 'present' if (packages[pkg] / path).exists() else 'missing'
                else:
                    external.add(pkg)
                references.append({'file': p.relative_to(ROOT).as_posix(), 'package': pkg, 'path': path, 'state': state})
            for pkg, path in re.findall(r'package://([^/]+)/([^\s"<>]+)', text):
                state = 'present' if pkg in packages and (packages[pkg] / path).exists() else 'missing'
                references.append({'file': p.relative_to(ROOT).as_posix(), 'package': pkg, 'path': path, 'state': state})
    failures.extend('missing CMake operand: ' + x for x in build_missing)
    failures.extend('missing active resource: ' + x['file'] + ' -> ' + x['path'] for x in references if x['state'] == 'missing')
    guarded = ['deepbot/launch/bringup.launch', 'deepbot_driver/launch/deepbot_driver.launch',
               'uvc_camera/launch/dual_camera.launch', 'deepbot_description/launch/display.launch']
    guard_results = {}
    for rel in guarded:
        root = ET.parse(WS / 'src' / rel).getroot()
        disabled = {x.get('name') for x in root.findall('arg') if x.get('default') == 'false'}
        unguarded = []
        def walk(node, gated=False):
            gated = gated or node.get('if') in {'$(arg ' + n + ')' for n in disabled}
            if node.tag in {'node', 'include'} and not gated:
                unguarded.append(node.attrib)
            for child in node:
                walk(child, gated)
        walk(root)
        guard_results[rel] = {'disabled_args': sorted(disabled), 'unguarded_nodes_or_includes': unguarded}
        if unguarded:
            failures.append('unguarded entry: ' + rel)
    secret = re.compile(rb'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----|(?:ghp_|github_pat_|sk-proj-)[A-Za-z0-9_]{16,}|(?:password|passwd|api_key|access_token|secret_key)\s*[:=]\s*[\x22\x27][^\x22\x27]{8,}', re.I)
    files = []
    for path in sorted(WS.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if path.suffix.lower() not in {'.stl', '.dae', '.mesh'} and secret.search(path.read_bytes()):
            failures.append('credential-like literal requires review: ' + rel)
        files.append({'path': rel, 'bytes': path.stat().st_size, 'sha256': digest(path),
                      'source_recorded': rel in mapped})
    result = {'scope': 'static source/resource/provenance checks only; no catkin, hardware or source execution',
              'active_packages': sorted(packages), 'legacy_catkin_ignored': True,
              'file_count': len(files), 'bytes': sum(x['bytes'] for x in files),
              'mapped_source_files': len(mapped), 'modified_source_files': changed,
              'new_files': [x['path'] for x in files if not x['source_recorded']],
              'resource_references': references, 'external_launch_packages': sorted(external),
              'guarded_entries': guard_results, 'failures': failures,
              'static_pass': not failures, 'catkin_compilation': 'not_run_no_usable_Linux_ROS',
              'hardware_validation': False}
    (DOCS / 'WORKSPACE_FILES.json').write_text(json.dumps(files, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (DOCS / 'VALIDATION.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('active_packages','file_count','bytes','mapped_source_files','modified_source_files','failures','static_pass')}, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == '__main__':
    raise SystemExit(main())
