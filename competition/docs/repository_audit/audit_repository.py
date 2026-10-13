"""Read-only source/ZIP static inventory. Writes only alongside this script.

No source execution, build, extraction, network, hardware or Git mutation.
Not a full CMake evaluator: dynamic references are recorded as unresolved.
"""
import argparse
from collections import Counter, defaultdict
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = ROOT/'vehicle_snapshot_20261013_readonly/source/home/deepbot/catkin_ws/src'
LICENSE = re.compile(r'^(licen[sc]e|copying|notice)(\..*)?$', re.I)


def rel(path, root=ROOT):
    return path.relative_to(root).as_posix()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text(path):
    return path.read_text(encoding='utf-8', errors='replace')


def enumerate_tree(root):
    if not root.exists():
        return dict(present=False)
    files = sorted(p for p in root.rglob('*') if p.is_file())
    packages, names = [], defaultdict(list)
    for file in files:
        if file.name != 'package.xml':
            continue
        try:
            xml = ET.parse(file).getroot()
            name = xml.findtext('name')
            deps = sorted({e.text for e in xml if e.tag.endswith('depend') and e.text})
            entry = dict(name=name, directory=rel(file.parent, root),
                         package_xml=rel(file, root), sha256=sha(file),
                         licenses=[e.text for e in xml.findall('license')],
                         dependencies=deps,
                         folder_name_differs=file.parent.name != name,
                         messages=[rel(p, root) for p in file.parent.glob('msg/*') if p.is_file()],
                         services=[rel(p, root) for p in file.parent.glob('srv/*') if p.is_file()])
            packages.append(entry)
            names[name].append(entry)
        except ET.ParseError as exc:
            packages.append(dict(package_xml=rel(file,root),parse_error=str(exc)))
    cmake_checks, launch_refs, nodes, targets, absolute_paths, imports = [], [], [], defaultdict(set), [], []
    notices=[]
    for p in packages:
        if not p.get('name'):
            continue
        directory=root/p['directory']
        cmake=directory/'CMakeLists.txt'
        p['cmake_present']=cmake.is_file()
        if not cmake.is_file():
            continue
        raw=text(cmake)
        clean=re.sub(r'#[^\n]*','',raw)
        components=re.search(r'find_package\(catkin\s+REQUIRED\s+COMPONENTS\s+([^)]*)\)',clean,re.S)
        p['cmake_catkin_components']=components[1].split() if components else []
        p['components_missing_from_package_xml']=sorted(set(p['cmake_catkin_components'])-set(p['dependencies']))
        for m in re.finditer(r'\bconfigure_file\s*\(\s*([^\s)]+)',clean):
            token=m[1].strip('"')
            cmake_checks.append(dict(file=rel(cmake,root),command='configure_file',reference=token,
                                     dynamic='$' in token,exists=(directory/token).exists() if '$' not in token else None))
        if 'catkin_python_setup()' in clean:
            cmake_checks.append(dict(file=rel(cmake,root),command='catkin_python_setup',reference='setup.py',dynamic=False,exists=(directory/'setup.py').exists()))
        for m in re.finditer(r'opencv_apps_add_nodelet\(\s*([\w]+)\s+',clean):
            targets[p['name']].add(m[1])
        for match in re.finditer(r'\b(add_executable|add_library|generate_dynamic_reconfigure_options|add_message_files|add_service_files|catkin_install_python)\s*\(([^)]*)\)',clean,re.S):
            command,body=match.groups()
            tokens=body.split()
            if command in ('add_executable','add_library') and tokens:
                targets[p['name']].add(tokens[0].replace('${PROJECT_NAME}',p['name']))
            for token in tokens:
                token=token.strip('"')
                if not re.search(r'\.(cpp|cc|c|h|hpp|msg|srv|cfg|py)$',token):
                    continue
                prefix='msg/' if command=='add_message_files' else 'srv/' if command=='add_service_files' else ''
                candidate=directory/(prefix+token)
                cmake_checks.append(dict(file=rel(cmake,root),command=command,reference=prefix+token,
                                         dynamic='$' in token,
                                         exists=candidate.exists() if '$' not in token else None))
        p['catkin_install_python_present']='catkin_install_python(' in clean
    for file in files:
        if file.suffix.lower() not in ('.launch','.py','.cpp','.h','.hpp','.yaml','.cfg','.urdf','.xacro') and file.name!='CMakeLists.txt':
            continue
        raw=text(file)
        if file.suffix.lower() in ('.h','.hpp','.cpp','.c'):
            evidence=[dict(line=i+1,text=line.strip()) for i,line in enumerate(raw.splitlines()[:80])
                      if re.search(r'copyright|license|licence|redistribution|reserved|GNU General',line,re.I)]
            if evidence:
                notices.append(dict(file=rel(file,root),evidence=evidence))
        for line_no,line in enumerate(raw.splitlines(),1):
            # Store only path expressions, never complete credential-bearing lines.
            for match in re.finditer(r'/home/[^\s\"\x27<>;)]+',line):
                absolute_paths.append(dict(file=rel(file,root),line=line_no,path=match.group()))
            if file.suffix=='.py':
                match=re.match(r'\s*from\s+([\w.]+)\.(msg|srv)\s+import\s+(.+)',line)
                if match:
                    imports.append(dict(file=rel(file,root),line=line_no,package=match[1],kind=match[2],symbols=match[3].split('#')[0].strip()))
        if file.suffix!='.launch':
            continue
        # Parse XML so commented launch examples are not treated as active.
        try:
            xml=ET.fromstring(raw)
        except ET.ParseError as exc:
            launch_refs.append(dict(file=rel(file,root),parse_error=str(exc)))
            continue
        for element in xml.iter():
            for key,value in element.attrib.items():
                for m in re.finditer(r'\$\(find\s+([^)]+)\)([^\s\"\x27<>]*)',value):
                    name,suffix=m.groups()
                    local=names.get(name,[])
                    dynamic='$' in suffix
                    resolved=(root/local[0]['directory']/suffix.lstrip('/')) if len(local)==1 else None
                    launch_refs.append(dict(file=rel(file,root),tag=element.tag,attribute=key,package=name,
                                            suffix=suffix,dynamic=dynamic,local_package_count=len(local),
                                            exists=resolved.exists() if resolved is not None and not dynamic else None))
            if element.tag=='node':
                name,kind=element.get('pkg'),element.get('type')
                local=names.get(name,[])
                scripts=[]
                if len(local)==1 and kind and '$' not in kind:
                    scripts=[rel(p,root) for p in (root/local[0]['directory']).rglob(kind) if p.is_file()]
                nodes.append(dict(file=rel(file,root),package=name,type=kind,local_package_count=len(local),
                                  executable_target=kind in targets.get(name,set()),script_matches=scripts))
    license_files=[dict(file=rel(p,root),sha256=sha(p),bytes=p.stat().st_size) for p in files if LICENSE.match(p.name)]
    return dict(present=True,root=rel(root),file_count=len(files),packages=packages,
                package_count=len(packages),license_files=license_files,
                duplicate_packages={n:[p['directory'] for p in ps] for n,ps in names.items() if len(ps)>1},
                license_declarations=dict(Counter(l for p in packages for l in p.get('licenses',[]))),
                cmake_file_references=cmake_checks,launch_references=launch_refs,launch_nodes=nodes,
                hardcoded_home_paths=absolute_paths,python_message_imports=imports,
                source_header_notices=notices,
                source_files=[dict(file=rel(p,root),bytes=p.stat().st_size,sha256=sha(p)) for p in files])


def d_inventory():
    root=Path('D:/智能驾驶赛')
    files=sorted(p for p in root.rglob('*') if p.is_file() and not {'.venv','.git','__pycache__'}.intersection(p.relative_to(root).parts))
    archives=[]
    for file in files:
        if file.suffix.lower()!='.zip':
            continue
        item=dict(file=rel(file,root),bytes=file.stat().st_size)
        try:
            with zipfile.ZipFile(file) as archive:
                members=archive.infolist()
                found=[m for m in members if LICENSE.match(Path(m.filename).name)]
                item.update(member_count=len(members),license_members=[],
                            package_xml_members=[m.filename for m in members if Path(m.filename).name=='package.xml'],
                            nested_archives=[m.filename for m in members if Path(m.filename).suffix.lower() in ('.zip','.rar')])
                for member in found:
                    entry=dict(member=member.filename,bytes=member.file_size)
                    if member.file_size<=1048576:
                        data=archive.read(member)
                        entry['sha256']=hashlib.sha256(data).hexdigest()
                        if Path(member.filename).suffix.lower() in ('','.txt','.md','.rst'):
                            entry['text']=data.decode('utf-8',errors='replace')
                        else:
                            entry['content_status']='binary_license_not_text_decoded'
                    item['license_members'].append(entry)
                # Source headers from two explicit MCU source archives only.
                if file.name in ('robot-x4.zip','robot_x4_bsp_0606.zip'):
                    headers=[]
                    for member in members:
                        if Path(member.filename).suffix.lower() not in ('.c','.h') or member.file_size>1048576:
                            continue
                        raw=archive.read(member).decode('utf-8',errors='replace')
                        first=raw.splitlines()[:75]
                        evidence=[dict(line=i+1,text=line.strip()) for i,line in enumerate(first)
                                  if re.search(r'copyright|license|licence|redistribution|reserved|STMicroelectronics',line,re.I)]
                        if evidence:
                            headers.append(dict(member=member.filename,evidence=evidence))
                    item['source_header_notices']=headers
        except (OSError,zipfile.BadZipFile) as exc:
            item['error']=str(exc)
        archives.append(item)
    return dict(root='D:/智能驾驶赛',file_count=len(files),
                unpacked_license_files=[rel(p,root) for p in files if LICENSE.match(p.name)],
                unpacked_package_xml=[rel(p,root) for p in files if p.name=='package.xml'],
                zip_archives=archives,rar_not_opened=[rel(p,root) for p in files if p.suffix.lower()=='.rar'],
                limitations='ZIP member metadata only except <=1MiB license members and headers in the two named MCU source ZIPs; no image restoration or nested archive extraction.')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--phase',choices=('initial','final'),default='initial')
    args=parser.parse_args()
    snapshot_file=HERE/'initial_inventory.json'
    if args.phase=='initial':
        result=dict(snapshot=enumerate_tree(SOURCE),d_drive=d_inventory())
        snapshot_file.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    else:
        result=json.loads(snapshot_file.read_text(encoding='utf-8'))
        previous=HERE/'audit.json'
        if previous.exists():
            old=json.loads(previous.read_text(encoding='utf-8'))
            result['initial_findings']=old.get('findings',old.get('initial_findings',[]))
    result.update(phase=args.phase,created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  git_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                  vehicle_ws=enumerate_tree(ROOT/'vehicle_ws/src'),
                  legacy_packages=enumerate_tree(ROOT/'vehicle_ws/legacy_packages'),
                  combined_workspace=enumerate_tree(ROOT/'vehicle_ws'),
                  claims=dict(ros_compilation='NOT_RUN_WINDOWS_NO_ROS',hardware='NOT_ACCESSED',
                              deployment='NOT_VALIDATED',offline_tests='NOT_RERUN_IN_THIS_READ_ONLY_AUDIT'))
    result['git_index_modes']=[dict(mode=line.split()[0],path=line.split('\t',1)[1]) for line in
         subprocess.check_output(['git','ls-files','-s','vehicle_ws'],cwd=ROOT,text=True,encoding='utf-8').splitlines()]
    (HERE/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    for label in ('snapshot','vehicle_ws'):
        r=result[label]
        if r['present']:
            print(label,'packages',r['package_count'],'files',r['file_count'],'licenses',r['license_declarations'])
            print('literal CMake missing',sum(x['exists'] is False for x in r['cmake_file_references']),
                  'launch local missing',sum(x.get('exists') is False for x in r['launch_references']))
        else:
            print(label,'not present')
    print('D ZIPs',len(result['d_drive']['zip_archives']))


if __name__=='__main__':
    main()
