"""Independent byte/resource verification; writes only repository_audit."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    docs=ROOT/'competition/docs/vehicle_source'
    rows=json.loads((docs/'WORKSPACE_FILES.json').read_text(encoding='utf-8'))
    sources=json.loads((docs/'SOURCE_INVENTORY.json').read_text(encoding='utf-8'))
    result=dict(scope='independent local static and byte checks; no build/source execution/hardware',
                workspace_manifest_entries=len(rows),workspace_missing=[],workspace_hash_mismatch=[],
                original_source_missing=[],original_source_hash_mismatch=[],
                recorded_destination_hash_mismatch=[],modified_files=[],mapped_source_count=0,
                urdf_resource_checks=[],git_filter_checks=[],guard_checks=[],
                core_python_files=[],unlisted_workspace_files=[],executable_manifest_issues=[],documentation_links=[])
    for row in rows:
        path=ROOT/row['path']
        if not path.is_file():
            result['workspace_missing'].append(row['path'])
        elif digest(path)!=row['sha256']:
            result['workspace_hash_mismatch'].append(row['path'])
    listed={row['path'] for row in rows}
    result['unlisted_workspace_files']=[p.relative_to(ROOT).as_posix() for p in (ROOT/'vehicle_ws').rglob('*')
                                        if p.is_file() and p.relative_to(ROOT).as_posix() not in listed]
    for row in sources:
        if not row.get('destination'):
            continue
        result['mapped_source_count']+=1
        source=ROOT/row.get('snapshot','vehicle_snapshot_20261013_readonly')/row['source']
        if not source.is_file():
            result['original_source_missing'].append(row['source'])
        elif digest(source)!=row['source_sha256']:
            result['original_source_hash_mismatch'].append(row['source'])
        dest=ROOT/row['destination']
        if dest.is_file():
            sha=digest(dest)
            if row.get('destination_sha256') and sha!=row['destination_sha256']:
                result['recorded_destination_hash_mismatch'].append(row['destination'])
            if sha!=row['source_sha256']:
                result['modified_files'].append(row['destination'])
    packages={ET.parse(p).getroot().findtext('name'):p.parent for p in (ROOT/'vehicle_ws/src').rglob('package.xml')}
    result['active_packages']=sorted(packages)
    result['legacy_ignored']=(ROOT/'vehicle_ws/legacy_packages/CATKIN_IGNORE').is_file()
    executable_list=docs/'EXECUTABLE_FILES.txt'
    if executable_list.exists():
        names=executable_list.read_text(encoding='utf-8').splitlines()
        result['executable_manifest_count']=len(names)
        for name in names:
            path=ROOT/name
            if not path.is_file():
                result['executable_manifest_issues'].append(dict(file=name,issue='missing'))
                continue
            data=path.read_bytes()
            if not data.startswith(b'#!') or data.split(b'\n',1)[0].endswith(b'\r'):
                result['executable_manifest_issues'].append(dict(file=name,issue='missing_or_CRLF_shebang'))
    for file in (ROOT/'vehicle_ws/README.md',ROOT/'vehicle_ws/NOTICE.md'):
        if not file.exists():
            continue
        for target in re.findall(r'\]\(([^)]+)\)',file.read_text(encoding='utf-8')):
            if '://' not in target:
                result['documentation_links'].append(dict(file=file.relative_to(ROOT).as_posix(),target=target,
                        exists=(file.parent/target.split('#')[0]).exists()))
    for file in (ROOT/'vehicle_ws/src').rglob('*'):
        if file.suffix in ('.urdf','.xacro'):
            raw=file.read_text(encoding='utf-8',errors='replace')
            for m in re.finditer(r'package://([^/\s]+)/([^\s\"<>]+)',raw):
                package,path=m.groups()
                dest=packages.get(package)
                result['urdf_resource_checks'].append(dict(file=file.relative_to(ROOT).as_posix(),
                     uri=m[0],exists=bool(dest and (dest/path).is_file())))
        if file.suffix=='.py':
            data=file.read_bytes()
            result['core_python_files'].append(dict(file=file.relative_to(ROOT).as_posix(),
                    crlf_count=data.count(b'\r\n'),has_shebang=data.startswith(b'#!')))
    for name in ('deepbot/launch/bringup.launch','deepbot_driver/launch/deepbot_driver.launch','uvc_camera/launch/dual_camera.launch'):
        file=ROOT/'vehicle_ws/src'/name
        tree=ET.parse(file).getroot()
        default=next((a.get('default') for a in tree.findall('arg') if a.get('name')=='enable_hardware'),None)
        unguarded=[]
        def walk(node,guarded=False):
            guarded=guarded or (node.tag=='group' and node.get('if')=='$(arg enable_hardware)')
            if node.tag in ('node','include') and not guarded:
                unguarded.append(dict(tag=node.tag,package=node.get('pkg'),file=node.get('file')))
            for child in node:
                walk(child,guarded)
        walk(tree)
        result['guard_checks'].append(dict(file=name,default=default,unguarded_nodes_or_includes=unguarded))
    # hash-object has no -w: reads Git filters without writing index/object data.
    for name in ('vehicle_ws/src/deepbot_driver/CMakeLists.txt','vehicle_ws/src/uvc_camera/src/camera.cpp',
                 'vehicle_ws/legacy_packages/deepbot_auto_driver/scripts/auto_run.py'):
        if not (ROOT/name).exists():
            continue
        raw=subprocess.check_output(['git','hash-object','--no-filters',name],cwd=ROOT,text=True).strip()
        filtered=subprocess.check_output(['git','hash-object','--path='+name,name],cwd=ROOT,text=True).strip()
        attrs=subprocess.check_output(['git','check-attr','text','eol','--',name],cwd=ROOT,text=True).splitlines()
        result['git_filter_checks'].append(dict(file=name,raw_blob=raw,filtered_blob=filtered,
                                                byte_preserving=raw==filtered,attributes=attrs))
    (HERE/'delivery_checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('modified_files','urdf_resource_checks','git_filter_checks','guard_checks')},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
