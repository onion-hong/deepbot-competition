# B 数据工具交接：已实现离线最小链路

日期：2026-10-13。目标仍为 10-31，10-28 冻结功能。本轮只本地编码/合成测试，没有 SSH、真实相机/底盘启动、训练或速度发布。

## 当前版本与范围

cwd：`C:\Users\hongs\Documents\ChatGPT\智能驾驶赛`，分支 master。初始无提交，后续按总控协调在独占目录开发；A 初始基线为 `cd3d33415bbe4b753c1340a333ac6bc51e0c3927`，本交接收尾时只读核实 HEAD 已前进到 `7b5315d619c7bca37948f63bdf69a04b8806cc5b`（现场快照/交接文档）。**B 新文件仍未提交，这两个 HEAD 都不是 B 交付提交。** 本轮没有 Git 写操作。各会话写 code_commit=null、源码 SHA-256，不伪造版本。

仅修改 `competition/data_tools/` 与 `competition/tests/data_tools/`。公共接口、根 .gitignore、launch、历史源码和其他模块未修改。存储契约 deepbot.data/0.1.0，adapter 对接未改动的 deepbot.offline/0.1.0。前置审查产物仍保留，但“只有提案、没有代码”已被本交付替代。

| 文件 | 实现职责 |
|---|---|
| core.py | 配置校验、独占新会话、原始字节/消息/时钟、事件、状态、关闭/hash |
| offline.py | 原始/派生回读、逐相机配对审计、纠正排除、导出质量报告 |
| adapter.py | 可用帧→A 冻结 camera_frame；不能表达的时间状态明确省略并计数 |
| callback_gate.py | 收口后等待所有已接收回调，避免完整关闭后追加失败/漏数据 |
| ros_capture.py | 仅订阅已运行 ROS 1 流，不发命令、不启动设备/master |
| synthetic.py | 两个不同颜色/图案的有效 PNG 与独立合成流 |
| __main__.py / __init__.py | start/stop/event/export/inspect CLI 与格式版本 |
| synthetic.example.json | 虚构合成配置，不能当车载话题 |
| vehicle.visual.example.json | A 17:57 观察的静态配置候选；18:01 已离线，必须核对后使用 |
| requirements.txt / SCHEMA.md / README.md | 依赖、磁盘契约、入口 |
| tests/data_tools/test_data_tools.py、run_checks.py（位于 competition 下） | 26 项本地测试及持久证据输出 |
| evidence/ | 实际测试/样例报告；大部分原始测试产物在 outputs/ 保留 |

## 实际验证

- Python：`C:\Users\hongs\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`，3.12.14；Pillow 12.3.0。
- **26 项 B 离线测试通过，0 失败、0 跳过**。覆盖双路可回读、各自配对、恰好容差/超差/跨域拒绝、空 format/同 frame_id、重复物理身份/话题、缺流/坏图/旧时刻、跨流写入重排、关闭回调排空、停止/倒车/横移、纠正区间、缺标签、无覆盖、初始化/写盘/关闭失败、CLI 起停事件导出质检、ROS 缺依赖明确失败。
- A 原有 **13 项公共接口测试仍通过**；B 双路公共帧也经其 validate_stream 回读。
- 总控另行独立复跑 B 的 26 项测试，并完成 B→C 合成贯通。本轮已只读核实 `比赛实施方案_20261013/审查附件/总控贯通验收_20261013_03/ROOT_ACCEPTANCE.json`：6 帧→12 条公共记录，4 条道路有效、2 条无路无效，示范样本0。该贯通由总控执行，使用显式合成时刻，不是 B 实车或真实帧率结果；复现脚本为同附件目录的 verify_data_perception.py。
- 独立执行 CLI 合成短录：high 7、low 7，共 **14 张 64×48 有效 PNG**；导出、哈希及全量解码回读成功。两路图案不同；动作标签全部为空、示范样本 0，符合 visual_only。它不是 720P 现场验收。
- 合成运动用例：每路 4 帧，含停止、倒车、纯横移与纠正；每路配对 4，纠正排除 1，派生示范候选 3；原始 8 图像+4反馈全部保留。标签仍只是 synthetic 工程数据。
- 本机没有 rospy/rosbag，**未执行 ROS 传输、真实源接入、720P 双路吞吐、断电恢复或车辆运动验证**。仅对 ROS 适配做静态检查，运行了“缺依赖时非零退出、不建会话”的 CLI 测试。

详细证据：`evidence/LOCAL_TESTS.txt`、`LOCAL_TEST_RESULT.json`、`SAMPLE_VISUAL_QUALITY.json`、`SAMPLE_VISUAL_READBACK.json`、`SAMPLE_DEMONSTRATION_QUALITY.json`。原测试证据位于 `competition/tests/data_tools/outputs/check_e8e05be4abb743ceb872ae2f32304982/`，其 result.json 指向全部保留用例目录。

实际样例原始根：`competition/data_tools/outputs/synthetic_visual_20261013_01/`；导出根：`competition/data_tools/outputs/export_visual_20261013_01/`。这些路径相对本文件开头的实际 cwd。

已修复首轮发现的时钟等值误判和总控指出的跨流全局墙钟误判。另一次 Windows manifest 替换发生 PermissionError，现对同临时文件做有限重试；旧失败产物保留。最后通过的测试报告含最终 Python 源文件哈希。

## 本机复现（已运行；不接触硬件）

在 **Windows PowerShell、仓库根目录**执行。不要在仓库根盲跑全部历史测试。

```powershell
Set-Location 'C:\Users\hongs\Documents\ChatGPT\智能驾驶赛'
$dataPython = 'C:\Users\hongs\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $dataPython -X utf8 -B competition/tests/data_tools/run_checks.py
```

预期：26 tests OK，打印 TEST_EVIDENCE 新目录。失败表示对应本地数据行为未通过，查 tests.txt；不能改容差或删旧文件“让测试干净”。每次测试使用新 UUID 目录。

下面四步使用一个新会话名；两终端操作时将相同 session 路径复制到第二个终端，不重新生成名字。

```powershell
# 本地：准备路径。每次换新名字；旧目录存在将失败。
$dataSessionId = 'synthetic_' + [guid]::NewGuid().ToString('N')
$dataRoot = 'C:\Users\hongs\Documents\ChatGPT\智能驾驶赛\competition\data_tools\outputs'
$dataSession = Join-Path $dataRoot $dataSessionId
$dataExport = Join-Path $dataRoot ($dataSessionId + '_export')

# 1 本地开始合成记录，前台最多20秒。预期两路ready，反馈不要求存在。
& $dataPython -X utf8 -B -m competition.data_tools start --backend synthetic --config competition/data_tools/synthetic.example.json --root $dataRoot --session $dataSessionId --seconds 20

# 2 在另一个本地终端、记录仍运行时可提前结束；满20秒已CLOSED就跳过此命令。
# 现场对应步骤必须先停车；这个命令本身没有停车能力。
& $dataPython -X utf8 -B -m competition.data_tools stop --session $dataSession

# 3 本地离线导出。预期新images、samples、pair_audit、events、quality和manifest。
& $dataPython -X utf8 -B -m competition.data_tools export --session $dataSession --output $dataExport

# 4 本地回读原始和派生。报告写在会话外，避免改变冻结文件清单。
& $dataPython -X utf8 -B -m competition.data_tools inspect --session $dataSession --report ($dataSession + '_quality.json')
& $dataPython -X utf8 -B -m competition.data_tools inspect --export $dataExport --report ($dataExport + '_readback.json')
```

start：缺依赖/配置/重复输出/写盘失败退出非零；stop：仅请求结束，必须等 CLOSED 和 manifest.complete，已关闭再次 stop 会拒绝；export：不完整/哈希错/纠正事件不明确拒绝，质量不合格退出 2 并保留报告；inspect：完整且本地质量检查通过退出 0，否则 2。参数格式错误也返回非零。

`quality_ok=true` 只表示本地记录检查，不包含实物身份验收。visual_only 无反馈配对、动作标签 null 是正常结果；不能将此类数据冒充驾驶动作训练集。

记录时可加人工事件（相同环境/cwd，同一 session）：

```powershell
& $dataPython -X utf8 -B -m competition.data_tools event --session $dataSession --type correction --phase start --interval-id correction01 --reason '人工纠正开始'
& $dataPython -X utf8 -B -m competition.data_tools event --session $dataSession --type correction --phase end --interval-id correction01 --reason '人工纠正结束'
```

预期 EVENT_REQUESTED；到 events.jsonl 查 request_id 确认。事件时刻是记录器处理时刻，不能作为精确动作同步；重要区间以录像复核。先结束区间再停记录，遗漏 end 将保守排除后续所有示范样本。

## 给 A：无运动 20 秒真实双路采集卡（待现场验收，未执行）

从 A 的 `competition/docs/VEHICLE_HANDOFF.md` 得知：17:57 曾观察 high/low 各约30Hz、1280×720、format为空、frame_id相同、by-id/序列号冲突；**18:01相机/master已关闭，追加JPEG留样0帧且不完整**。这些不是 B 新记录器实测结果。当前不启动或重启相机；仅在 A 的下一次已授权现场窗口且两路已运行时使用以下卡。

准备：A 将本模块和冻结公共接口部署到一个明确目录，确认 Python3.8+、Pillow、rospy、sensor_msgs/nav_msgs/geometry_msgs 可导入，确认已有 ROS_MASTER_URI。Pillow 在车载是否安装尚未核实，不自动联网安装。核对 high/low 对应不同 USB by-path，而不是序列号或同 frame_id；将候选配置复制成现场配置，复核后更新 identity_verified/依据。数据根必须是新的可写目录，至少保留配置要求的1GiB余量。

以下为 **车载 Bash、A 已加载 Noetic 环境、A 指定的部署根目录**。路径由 A 填真实值；这些变量检查会阻止在位置未知时误运行。配置中仍然 feedback=null、command=null、visual_only/manual_visual/stationary，不为就绪开启底盘。

```bash
: "${DEEPBOT_REPO:?A填写已部署的仓库绝对目录}"
: "${DEEPBOT_DATA_ROOT:?A填写原始数据绝对根目录}"
: "${DEEPBOT_CONFIG:?A填写核对后的静态采集JSON绝对路径}"
: "${ROS_MASTER_URI:?A核对已经运行的ROS master}"
cd "$DEEPBOT_REPO"
python3 -c 'import sys, PIL, rospy; from sensor_msgs.msg import CompressedImage; print(sys.executable, PIL.__version__)'
DATA_SESSION="static_$(date +%Y%m%d_%H%M%S)_$(python3 -c 'import uuid; print(uuid.uuid4().hex[:8])')"
printf 'SESSION_PATH=%s/%s\n' "$DEEPBOT_DATA_ROOT" "$DATA_SESSION"

# 1 开始：仅订阅已运行相机，20秒自动结束；不启动相机/底盘/master。
python3 -B -m competition.data_tools start --backend ros --config "$DEEPBOT_CONFIG" --root "$DEEPBOT_DATA_ROOT" --session "$DATA_SESSION" --seconds 20

# 2 保持停车后结束：通常20秒已自动CLOSED，无需再stop。
# 如需提前结束，在第二个同环境终端填同一真实会话路径后执行：
# python3 -B -m competition.data_tools stop --session "$DEEPBOT_DATA_ROOT/$DATA_SESSION"

# 3 车载离线导出：回收文件后也可在装Pillow的本机运行同一命令。
python3 -B -m competition.data_tools export --session "$DEEPBOT_DATA_ROOT/$DATA_SESSION" --output "$DEEPBOT_DATA_ROOT/${DATA_SESSION}_export"

# 4 回读质检：原始和导出分别检查，报告放旁边。
python3 -B -m competition.data_tools inspect --session "$DEEPBOT_DATA_ROOT/$DATA_SESSION" --report "$DEEPBOT_DATA_ROOT/${DATA_SESSION}_quality.json"
python3 -B -m competition.data_tools inspect --export "$DEEPBOT_DATA_ROOT/${DATA_SESSION}_export" --report "$DEEPBOT_DATA_ROOT/${DATA_SESSION}_readback.json"
```

预期：两路独立计数、解码尺寸1280×720（若现场改了分辨率则如实记录）、无底盘反馈也 ready；结束 complete=true；每个收到的图像可在 raw 找到；feedback/command/human intent 为空、demonstration_eligible=false。实际帧数由现场测量，不以历史600帧/路强行断言成功。

失败含义：ROS_MASTER_URI缺失/master不在线→前检失败，不会替你启动；缺任一路超过启动宽限/运行过期→incomplete；空format但可解码应正常，坏字节则原样保留后异常结束；磁盘/关闭错误→非零，不完整；不同配置话题被ROS remap到同一路→拒绝；两路字节长期相同只报可疑，不能单凭静止同景判为同相机。

验收边界：乙查看两路首/中/尾及明显可区分的视野，对照安装映射确认来源；现场允许时由人做分路遮挡核对。软件检查不替代物理身份核实。高低相机的用途/朝向不由记录器推断；720P采集吞吐、USB带宽、每次写入fsync的负载、ROS排队/丢帧都还需要这次现场短录测量。

## 全赛道示范前还缺什么

1. 先完成以上真实双路静态短录/回读，并核实车载 Pillow 与 ROS 入口运行；本轮不能称已采到真实 JPEG。
2. A 确认必要 Odometry 真实话题/单位/坐标/符号/时间来源、底层手柄是否有可订阅命令，以及校准误差。不要因 topic 不存在就启动底盘补齐。
3. 新建 demonstration 配置，明确 manual_demonstration/joystick；冻结各路时间依据、容差和采样质量门槛。现接口用一个显式容差，若要各对不同容差需版本化扩展，不能自动放宽。
4. 完成源断流、坏图、磁盘不足/写盘错误、退出/停止后的真实短段验收；当前是合成注入证据，不是物理拔线/磁盘满验收。
5. 配置纠正/搬车/接管等人工区间与录像对齐；按整会话划分 development/validation，记录 validation consumed。静态和手推画面不生成驾驶意图。
6. 本版只持久化配置的两相机、Odometry 和 Twist 观测。IMU/sonar/自定义任务消息的通用订阅、离线补标版本管理、bag重建、断电恢复还未实现；需要时由 A 冻结映射，B 再扩展。不能把本版说成正式赛所有传感器已覆盖。

A 负责代码归档/提交、真实接入和最终合并。没有修改旧 data_collect.py，更没有运行它；无删除旧数据的清理步骤。本次最小链路已经可在本机执行，下一关是 A 的受控静态双相机验收。
