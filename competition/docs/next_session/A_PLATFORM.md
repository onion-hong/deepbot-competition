# A现场接入卡：手柄直道＋普通弯道采集

2026-10-13准备；依据NEXT_SESSION_PLAN。**本轮只读本地代码/旧快照，没有SSH、启动设备或运行现场命令。** 用户已确认手柄前进/转弯/停车正常，直接沿用。取消独立静止20秒关卡；摆位确认画面后，同一会话开始有用路段。下面是待到场执行的分支，不是一键已验收脚本。

## 0 一次填好路径，独立部署

到场只需告知总控“准备手柄采集”，总控按已有授权协调A接入；沿用有效连接配置，失效时只补当前地址/连接方式。A确认本次提交号、实际可写数据目录/剩余空间；不用用户重复证明手柄能力。

总控在本机将**本次最终提交**的 `competition/` 用 `git archive --format=tar --output=<新的本地tar路径> <完整提交号> competition` 打包，经现有SSH配置用scp传到小车一个新文件名。Git由总控执行；不用运行pip安装包的setup.py，也不把vehicle_ws整体覆盖到车上。到场后A填写并打印这些值：

| 值 | 填写与用途 |
|---|---|
| `DEPLOY_COMMIT` | 总控最终完整提交号，不能用准备阶段HEAD冒充新操作包版本 |
| `DEPLOY` | 新绝对目录，例如 `/home/deepbot/deepbot_competition/releases/<提交短号>_<本次编号>` |
| `ARCHIVE` | 已上传到新文件名的tar绝对路径；本机与车上SHA-256相同 |
| `ARCHIVE_SHA256` | 总控对本机tar执行Get-FileHash -Algorithm SHA256所得哈希 |
| `DATA_ROOT` | 本次已确认可写、空间足够的新数据根；不放Git，不指向旧训练目录 |

车载Bash，变量由A填真实值后执行；目录已存在就换新编号，不覆盖：

```bash
: "${DEPLOY_COMMIT:?填最终提交号}" "${DEPLOY:?填新绝对目录}" "${ARCHIVE:?填上传tar路径}" "${ARCHIVE_SHA256:?填本机tar哈希}" "${DATA_ROOT:?填数据根}"
test ! -e "$DEPLOY" || { echo '部署目录已存在，停止并换新目录'; exit 1; }
printf '%s  %s\n' "$ARCHIVE_SHA256" "$ARCHIVE" | sha256sum -c - || exit 1
mkdir -p "$(dirname "$DEPLOY")" || exit 1
mkdir "$DEPLOY" || exit 1
tar -xf "$ARCHIVE" -C "$DEPLOY" || exit 1
printf '%s\n' "$DEPLOY_COMMIT" > "$DEPLOY/DEPLOY_COMMIT.txt"
source /opt/ros/noetic/setup.bash || exit 1
source /home/deepbot/catkin_ws/devel/setup.bash || exit 1  # 复用原ROS环境
cd "$DEPLOY" || exit 1
export PYTHON_BIN=/usr/bin/python3
"$PYTHON_BIN" -B -c 'import sys,PIL,rospy; from sensor_msgs.msg import CompressedImage; from nav_msgs.msg import Odometry; from geometry_msgs.msg import Twist; import competition.data_tools; assert int(PIL.__version__.split(".")[0]) >= 9; print(sys.executable,sys.version,PIL.__version__,PIL.__file__,competition.data_tools.__file__)'
df -h "$DATA_ROOT"                    # 若尚未创建，先检查其已存在父目录，再建新数据根
```

核对模块路径确实落在`DEPLOY`，而非旧副本。ROS/Python3.8曾核实可用，**车载Pillow尚未核实**（requirements为Pillow≥9）。导入/版本不满足时只解决记录器依赖；不全局升级、不因缺Pillow重编译ROS包。压缩包/新目录建立不触发设备。不要source新vehicle_ws的devel，更不运行旧`data_collect.py`。

**仅Pillow缺失/版本不满足的分支，待现场执行：** 先确认`/usr/bin/python3`仍为3.8及ROS导入正常。用新目录的venv继承系统ROS包，只补固定`Pillow==10.4.0`，不安装其他requirements或升级全局pip。该版本声明支持Python≥3.8，发行页提供CPython3.8 Linux wheel：[Pillow 10.4.0](https://pypi.org/project/pillow/10.4.0/)。总控预先准备对应Linux x86_64/cp38 wheel并核对来源哈希，填WHEELHOUSE；本轮未创建venv、下载或安装。

```bash
/usr/bin/python3 -c 'import sys,rospy; assert sys.version_info[:2] == (3,8)' || exit 1
: "${WHEELHOUSE:?填已核对的离线wheel目录}"
VENV_PATH="$DEPLOY/capture_venv"
test ! -e "$VENV_PATH" || { echo '改用新venv目录，不覆盖'; exit 1; }
/usr/bin/python3 -m venv --system-site-packages "$VENV_PATH" || exit 1
export PYTHON_BIN="$VENV_PATH/bin/python"
"$PYTHON_BIN" -m pip install --no-index --find-links "$WHEELHOUSE" --only-binary=:all: --no-deps 'Pillow==10.4.0' || exit 1
"$PYTHON_BIN" -B -c 'import sys,PIL,rospy,sensor_msgs.msg,nav_msgs.msg,geometry_msgs.msg; import competition.data_tools; assert PIL.__version__ == "10.4.0"; print(sys.executable,sys.prefix,PIL.__version__,PIL.__file__,competition.data_tools.__file__)' || exit 1
```

若venv模块/ensurepip或对应wheel缺失，只报告这一依赖缺口，由总控准备环境；不自动sudo/联网安装。**A生成配置、B录制/导出/inspect都使用A最后通过检查的同一个绝对`PYTHON_BIN`**，不用泛指python3。交给B实际路径；B卡已强制沿用A提供的`PYTHON_BIN`，不会覆盖A的venv选择。新终端重新加载原ROS环境并赋相同变量。

## 1 看当前状态，再选择唯一分支

在同一车载环境只读查询：

```bash
printf 'ROS_MASTER_URI=%s\n' "${ROS_MASTER_URI:-UNSET}"
ss -ltnp 'sport = :11311'
pgrep -a -f '(^|/)(roscore|rosmaster|uvc_camera_node)( |$)' || true
ls -l /dev/v4l/by-path/
fuser /dev/video0 /dev/video2          # 只列占用，不带-k；权限不足不能解释为无人占用
# 仅在URI已经确认时查询；失败先区分URI/网络/服务状态，不能直接另起master。
timeout 4s rosnode list
timeout 4s rostopic list
```

| 现场状态 | A操作 |
|---|---|
| master、两路相机已有数据 | 全部复用；`rostopic info <实际相机话题>`与`rosnode info <实际节点>`核对发布者。不得用同名新节点顶掉旧节点 |
| master在线，只缺一路/两路相机 | 先核对缺路设备占用和节点名；只启动缺的一路。不运行双相机launch去替换仍在线的另一路 |
| 本机master确实不存在，且已排除URI指向另一台现有master | A在单独标记“A本次master”的前台终端运行`roscore`；本机各终端明确使用`export ROS_MASTER_URI=http://127.0.0.1:11311`。这是全部ROS参与者在车上运行的分支；不覆盖既有多机ROS网络配置 |
| 有设备占用但无预期流、master失联、同名节点归属不清 | 只定位对应PID/节点/日志，由总控确认归属；不杀未知进程，不在占用设备上抢开第二个驱动 |

若graph显示旧自动驾驶也可能发速度，先通过其实际`cmd_vel`话题的`rostopic info`识别发布者，由总控处理冲突；不启动新底盘、不中断已好用的手柄链路。本次B记录器没有Publisher，不需要为了feedback为空启动底盘。

**历史仅作定位：** 10-13 17:57曾有`/camera_high`、`/camera_low`；18:01旧master/相机离线。那不是到场时的事实。历史设备角色为video0高、video2低；by-path分别USB端口3和2，不能根据相同serial/by-id或共同frame_id=camera识别两路。

## 2 缺路时才启动已有相机二进制

实际快照确认可执行文件为 `/home/deepbot/catkin_ws/devel/lib/uvc_camera/uvc_camera_node`；历史参数1280×720、30fps、format=jpeg。源码`camera_node.cpp`使用普通命名空间发布，`camera.cpp`的JPEG话题名是`image_raw/compressed`。以下显式重映射由此核对得出，**本组合本轮未在设备上执行**；不需要先编译7包。

各用一个前台终端，仅运行缺路对应的一条；终端先source上述原ROS环境并使用已核实的ROS_MASTER_URI。A把HIGH_DEVICE/LOW_DEVICE设为本次确认的不同by-path或实际video节点：

```bash
# 高路缺失且设备可用时；若camera_high已有节点，先识别，不能直接使用同名覆盖。
: "${HIGH_DEVICE:?填本次核实的高位设备}"
/home/deepbot/catkin_ws/devel/lib/uvc_camera/uvc_camera_node \
  __name:=camera_high _device:="$HIGH_DEVICE" _width:=1280 _height:=720 _fps:=30 _format:=jpeg \
  image_raw/compressed:=/camera_high/image_raw/compressed camera_info:=/camera_high/camera_info
```

```bash
# 低路缺失且设备可用时。
: "${LOW_DEVICE:?填本次核实的低位设备}"
/home/deepbot/catkin_ws/devel/lib/uvc_camera/uvc_camera_node \
  __name:=camera_low _device:="$LOW_DEVICE" _width:=1280 _height:=720 _fps:=30 _format:=jpeg \
  image_raw/compressed:=/camera_low/image_raw/compressed camera_info:=/camera_low/camera_info
```

先`test -x`确认该二进制仍在；缺失/启动报库错误就收集这条错误，不切换整套bringup碰运气。运行期间保留前台日志。已有相机若采用别的话题/分辨率，配置B去匹配真实流；不为迁就上面示例重启它。源码归档中的dual_camera.launch默认关闭且尚未实测，本次优先上述原二进制与已有流，不要求运行新launch。

## 3 同一采集会话确认两路，然后直接走首段

复用现有图像查看器；需要时在**车载图形桌面**运行`rosrun rqt_image_view rqt_image_view`，选择实际compressed话题。SSH没有DISPLAY时不硬填`:0`；由桌面查看器或B提供的首帧预览确认。A/乙对照安装高度和不同视野，必要时逐路短暂遮挡辨认；画面确认与正常摆位一起完成，不另等20秒。

**A生成VERIFIED_CONFIG后交给B，不能只口述字段。** 下面在车载交互Bash执行：从已部署的`vehicle.visual.example.json`复制内容，改成本次核实值，在仓库外独占创建唯一JSON。先确认两路画面身份，再按查询/观测填写；不要照抄历史节点/设备。每路的evidence写本次核对时间、topic→设备→安装高度依据及来源时钟依据。`physical_id`用已确认的USB端口/设备身份，不用同名serial。`message_type`自动只读查询实际topic。

时钟填写规则：只有核对当前发布者、驱动时间戳来源及ROS时间域后，才填有依据的source_clock_id；确实同域的两路使用相同ID。只有证实该域与记录器当前ROS时间可比较，才答ROS_TIME_COMPARABLE=yes（检查`/use_sim_time`及已有header；不是只看两数字相近）。未证实填unknown/no，选择receipt_approximate；不能自动填true或伪造曝光时钟。未知域且非零原stamp可能被公共adapter省略，须向C报告公共清单覆盖不足；原始图像仍保留，不抹原stamp来绕过校验。

```bash
export REPO_ROOT="$DEPLOY" DATA_ROOT PYTHON_BIN
cd "$REPO_ROOT" || exit 1
export VERIFIED_CONFIG="$DATA_ROOT/site_configs/verified_$("$PYTHON_BIN" -c 'import uuid; print(uuid.uuid4().hex)').json"
for role in HIGH LOW; do
  for field in TOPIC DEVICE_KEY PHYSICAL_ID EVIDENCE SOURCE_CLOCK_ID IDENTITY_CONFIRMED ROS_TIME_COMPARABLE; do
    read -r -p "$role $field（确认项只填yes/no；未知时钟填unknown）：" value
    export "${role}_${field}=$value"
  done
done
read -r -p '配对依据source_header或receipt_approximate：' PAIRING_BASIS
export PAIRING_BASIS
"$PYTHON_BIN" -B - <<'PY'
import json, os, subprocess
from pathlib import Path
from competition.data_tools.core import load_json, validate_config
repo = Path(os.environ['REPO_ROOT']).resolve()
root = Path(os.environ['DATA_ROOT']).resolve()
target = Path(os.environ['VERIFIED_CONFIG']).resolve()
if root == repo or repo in root.parents or root not in target.parents:
    raise ValueError('配置和数据必须位于仓库外的DATA_ROOT')
c = load_json(repo / 'competition/data_tools/vehicle.visual.example.json')
c.update(mode='visual_only', role='manual_visual', acquisition_method='joystick',
         split='development', feedback=None, command=None)
c['snapshot_note'] = 'Current A verification; per-camera evidence below. No hardware synchronization claim.'
for role in ('high', 'low'):
    def supplied(key):
        value = os.environ[role.upper() + '_' + key].strip()
        if not value: raise ValueError(role + ': empty ' + key)
        return value
    if supplied('IDENTITY_CONFIRMED') != 'yes':
        raise ValueError(role + ': 身份未确认，暂不签发VERIFIED_CONFIG')
    comparable = supplied('ROS_TIME_COMPARABLE')
    if comparable not in ('yes', 'no'): raise ValueError('ROS_TIME_COMPARABLE must be yes/no')
    spec = c['cameras'][role]
    spec.update(topic=supplied('TOPIC'), device_key=supplied('DEVICE_KEY'),
                physical_id=supplied('PHYSICAL_ID'), identity_evidence=supplied('EVIDENCE'),
                identity_verified=True, source_clock_id=supplied('SOURCE_CLOCK_ID'),
                compare_source_to_ros_time=comparable == 'yes')
    spec['message_type'] = subprocess.check_output(
        ['rostopic', 'type', spec['topic']], text=True, timeout=5).strip()
basis = os.environ['PAIRING_BASIS'].strip()
domains = {s['source_clock_id'] for s in c['cameras'].values()}
if basis == 'source_header' and ('unknown' in domains or len(domains) != 1):
    raise ValueError('source_header requires a confirmed shared source clock')
c['pairing'].update(basis=basis, scope='first_joystick_visual_segment_engineering_only')
# 原模板容差/新鲜性/空间门槛不自动放宽；不以此证明现场同步或吞吐。
c = validate_config(c)
print(json.dumps(c, ensure_ascii=False, indent=2))
target.parent.mkdir(parents=True, exist_ok=True)
with target.open('x', encoding='utf-8') as f:
    json.dump(c, f, ensure_ascii=False, indent=2)
print('VERIFIED_CONFIG=' + str(target))
PY
```

任一错误停止，不把未生成的路径交给B。成功后A回读`cat "$VERIFIED_CONFIG"`核对无误，再交付：**REPO_ROOT（即DEPLOY）、DATA_ROOT、VERIFIED_CONFIG、PYTHON_BIN、DEPLOY_COMMIT、当前ROS_MASTER_URI**。B据此派生其会话配置，保持两路身份/时钟事实。空CompressedImage.format本身不是坏图；不能从0×0 CameraInfo读取尺寸。

按[B_CAPTURE.md](B_CAPTURE.md)开始**同一会话**：当前CLI为`start --backend ros --config ... --root ... --session ... --seconds ...`。必须显式填写覆盖拟采路段的最长运行时限，CLI默认20秒会自动结束，不能漏写；时限不是要求停留的采集关卡。乙看到两路`streams`计数都在增加、`ready=true`后，甲按熟悉手柄速度走直道＋普通弯道。先确保图像有用，不启动自主控制。录制中缺流/坏图/写盘异常即停车定位，不继续无数据行驶。

甲停车后B发`stop --session <同一会话路径>`并等`CLOSED complete=true`；stop只停记录，不停车。随后立即导出/inspect，抽看两路首/中/尾和弯道/纠正处，由C回放。原始失败数据保留，单次成功不等于长录吞吐验收。若只有甲一人，先设置合适时限并确认正在记录，驾驶时不操作终端，停车后再收尾。

## 4 只收本次自启进程

A记录“终端标签—用途—节点名—实际PID—是否本次创建”。本次相机/master均前台运行：停车、B正常关闭后，仅在对应**自启终端**按Ctrl-C，观察该进程退出；不关闭复用的相机/查看器/手柄进程。仅当没有其他人在复用本次master时才结束它。终端丢失时先按节点/PID和启动记录核对身份，再定点处理，不把`fuser`列出的所有PID当成可杀清单。禁止killall、批量pkill、整体重启。数据传回完整会话与导出目录，校验哈希，不把原图推到公有Git。

## 真缺口及后续自主动作

现场要补的只有：当前连接/ROS图与设备映射、实际Pillow/ROS导入、最终部署提交和可写数据位置、首段真实记录/关闭/回读表现。车载整套7包重编译不是首段视觉采集门槛；本卡不重复确认手柄整套能力。

**A下一项定向开发：E复核P1-02。** 新归档driver的`ReadFormSerial()`按一次available读块当整帧，先访问rxbuf[0]/[1]且后续取到[21]，缺最小长度、缓存拆包/粘包处理；watchdog在同一循环串口读取之后，0.5秒常数不证明异常下的实际停车时延。首次启用**新自主控制链路**前，由总控另授A源码范围，按真实协议修复长度/分帧/校验并针对短帧、拆包、粘包、反馈中断做离线验证，再在授权窗口测停车。依据见[独立复核P1-02](../decision_review/REVIEW_NEXT_SESSION.md)。本轮不修改/替换用户当前手柄驱动，也不以此阻塞纯视觉采集。

新自主程序仍缺可执行控制器与真实接入。后续另获自主窗口后，先用首个短动作验证**新增链路**的速度单位、前后/转向符号、主动零速和超时停车，并用反馈＋外部实际位移/转角/停距记录对照；手柄正常不能替代这些关系。通过后，依据测得的图像/控制延迟、转弯曲率与跟踪误差、可用路段净空和停车距离及时提高到有代表性的工作速度，不一直慢爬，也不在无依据时填写m/s或rad/s。感知失效、延迟异常、出界趋势或停车异常时停止这一项并定位，不重跑无关90项。
