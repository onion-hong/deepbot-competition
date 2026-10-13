# B：首段直道＋普通弯道手柄视觉采集卡

2026-10-13，按[下一轮计划](../team/NEXT_SESSION_PLAN.md)执行。**不设独立静止20秒关卡；完成短路段就结束，停车后随即查数据。** 本卡现场命令待 A 接入验收；本轮没有连接车或启动 ROS。

已核实 `visual_only / manual_visual / acquisition_method=joystick` 被现有校验器支持；feedback、command 均可为 null，不等底盘反馈。首批只是视觉资料，不是模仿学习动作对，不谎记 stationary。高低相机不等于前后相机。

## 1．一次填写变量并生成本次配置（车载 Bash）

A 先提供已部署目录和**刚核实过**的两路配置，确认当前相机、master 已运行，实际身份/topic/type、来源时钟和 Python 依赖可用。B 不另启动它们。只核对这几项与数据盘余量；不重复整车检查，不直接把旧候选配置的身份/时钟状态当成今天的事实。

在 A 已加载 ROS 1 环境并设置 PYTHON_BIN 的同一个车载 Bash 粘贴本块，按提示填写三次路径。沿用 A 已核实的解释器（包括隔离环境路径），须能导入 Pillow、rospy 及 sensor_msgs/nav_msgs/geometry_msgs；未设置时停止，由 A 填写，不回退到系统 python3。VERIFIED_CONFIG 填 A 本次生成并核实的真实配置文件路径。

```bash
read -r -p '部署仓库绝对路径：' REPO_ROOT
read -r -p '仓库外的数据根目录：' DATA_ROOT
read -r -p 'A已核实的双相机配置JSON绝对路径：' VERIFIED_CONFIG
export REPO_ROOT DATA_ROOT VERIFIED_CONFIG
: "${PYTHON_BIN:?请由A设置已核实的解释器路径，沿用A的环境}"
export PYTHON_BIN
: "${ROS_MASTER_URI:?请A确认现有ROS环境，本卡不启动master}"
cd "$REPO_ROOT" || exit 1
"$PYTHON_BIN" -c 'import sys,PIL,rospy,sensor_msgs.msg,nav_msgs.msg,geometry_msgs.msg; print(sys.executable, PIL.__version__)' || exit 1
export SESSION="joystick_$(date +%Y%m%d_%H%M%S)_$("$PYTHON_BIN" -c 'import uuid; print(uuid.uuid4().hex[:8])')"
export RUN_DIR="$DATA_ROOT/runs/$SESSION"
export SESSION_PATH="$DATA_ROOT/raw/$SESSION"
export SITE_CONFIG="$RUN_DIR/capture.json"
export EXPORT_PATH="$DATA_ROOT/derived/${SESSION}_export"
"$PYTHON_BIN" - <<'PY' || exit 1
import json, os
from pathlib import Path
from competition.data_tools.core import load_json, validate_config
for key in ('REPO_ROOT', 'DATA_ROOT', 'VERIFIED_CONFIG'):
    if not Path(os.environ[key]).is_absolute():
        raise ValueError(key + ' must be an absolute path')
repo = Path(os.environ['REPO_ROOT']).resolve()
root = Path(os.environ['DATA_ROOT']).resolve()
if root == repo or repo in root.parents:
    raise ValueError('DATA_ROOT must be outside the repository')
c = load_json(os.environ['VERIFIED_CONFIG'])
c.update(mode='visual_only', role='manual_visual', acquisition_method='joystick',
         split='development', feedback=None, command=None)
c['capture_note'] = 'First straight and ordinary bend; joystick visual data; no action labels'
c = validate_config(c)  # 保留A核实的相机、时钟、容差及余量，不自动放宽
Path(os.environ['RUN_DIR']).mkdir(parents=True, exist_ok=False)
with Path(os.environ['SITE_CONFIG']).open('x', encoding='utf-8') as f:
    json.dump(c, f, ensure_ascii=False, indent=2)
print('CONFIG_READY', os.environ['SITE_CONFIG'])
print('SESSION_PATH', os.environ['SESSION_PATH'])
PY
```

预期依赖检查成功并打印 CONFIG_READY。任何报错先处理，不继续下面的 start。本次配置从已核实配置派生，只改用途字段；来源域未知时由 A 明确选择接收时间近似且禁止与 ROS 时间强行比较。历史50ms容差不是正式标准，不为了提高通过率改容差。所有会话、导出、报告使用新名字，不删旧文件。

## 2．开始：后台记录，前台看状态（同一个终端）

```bash
"$PYTHON_BIN" -u -B -m competition.data_tools start --backend ros --config "$SITE_CONFIG" --root "$DATA_ROOT/raw" --session "$SESSION" --seconds 600 > "$RUN_DIR/capture.log" 2>&1 &
CAPTURE_PID=$!
printf '本次记录PID=%s；会话=%s\n' "$CAPTURE_PID" "$SESSION_PATH"
tail -n +1 -f "$RUN_DIR/capture.log"
```

`start` 本身会阻塞；此卡把它放后台，当前前台只是 `tail` 看日志，变量不需在第二终端重填。看到 SESSION、`"ready": true`，high/low 两路计数都在增加，再用熟悉的手柄速度完成直道＋普通弯道。**600秒只是遗忘关闭时的录制上限，不是驾驶时长；默认20秒会过早结束，所以不可省略该参数。自动结束不会停车。**

人少时先专心驾驶，完成后停车再操作电脑；有人协作则乙看日志/记事件。报错、画面明显异常或意外 CLOSED 时停车处理。不关终端、不退出会话、不让记录后台无人看管。

## 3．正常结束／提前结束：先停车，再停记录

完成短路段或决定提前结束，先用手柄停好车。按 **Ctrl+C 退出前台 tail**，然后执行：

```bash
"$PYTHON_BIN" -B -m competition.data_tools stop --session "$SESSION_PATH"
wait "$CAPTURE_PID"
CAPTURE_RC=$?
printf '记录器退出码=%s\n' "$CAPTURE_RC"
tail -n 8 "$RUN_DIR/capture.log"
```

**这里 Ctrl+C 只停日志显示，没有停止后台记录，更不会停车。** 必须执行 stop 并等待。预期 STOP_REQUESTED，随后日志 CLOSED、complete=true、退出码0；再进入导出。若已自动 CLOSED，不重复 stop，只执行 wait 和读日志。提前结束使用同一流程，保留已经记录的短段。

## 4．事件：有需要时记录，不让司机边开边操作

记录仍在运行时，乙可按 Ctrl+C 暂停 tail 显示，在同一终端执行事件命令；后台记录仍继续。下列 start/end 分别在纠正开始/结束时执行，不是连续一次粘贴两条。每个区间换一个编号；EVENT_REQUESTED 后在 events.jsonl 核对 request_id，才算记录器已接收。

```bash
"$PYTHON_BIN" -B -m competition.data_tools event --session "$SESSION_PATH" --type correction --phase start --interval-id correction01 --reason 'manual correction begins'
# 纠正完成时再执行：
"$PYTHON_BIN" -B -m competition.data_tools event --session "$SESSION_PATH" --type correction --phase end --interval-id correction01 --reason 'manual correction ends'
# 普通路段提示用点事件，不伪装精确物理时刻：
"$PYTHON_BIN" -B -m competition.data_tools event --session "$SESSION_PATH" --type segment_note --reason 'ordinary bend'
```

可用 `tail -n 10 "$SESSION_PATH/events.jsonl"` 查接收结果，然后 `tail -n 5 -f "$RUN_DIR/capture.log"` 恢复看状态。事件时间是记录器收到请求的时间；没有旁人及时标注时，停车后在 RUN_DIR 另留人工说明/录像依据，**不要把事后事件时间冒充真实纠正开始时间**。本版没有事后补标 CLI。原始停止、倒车、横移、失败和纠正段都保留；将来派生示范才按区间排除，未闭合 start 会保守排除后续。

## 5．停车后马上导出、inspect（同终端；纯离线）

仅在正常完整关闭后执行。每条成功才继续下一条；非零退出先看错误，不反复使用同一输出名。

```bash
"$PYTHON_BIN" -B -m competition.data_tools export --session "$SESSION_PATH" --output "$EXPORT_PATH"
"$PYTHON_BIN" -B -m competition.data_tools inspect --session "$SESSION_PATH" --report "$RUN_DIR/raw_quality.json"
"$PYTHON_BIN" -B -m competition.data_tools inspect --export "$EXPORT_PATH" --report "$RUN_DIR/export_quality.json"
```

预期：原始会话有 raw/、receipts、events、frozen_config、manifest；导出有 images/high、images/low、samples、pair_audit、camera_pairs、camera_frames、quality 和派生 manifest。两路各有可解码图像，原始/派生哈希检查正常；measured_motion、observed_command、human_intent 均为空，demonstration_eligible=false。无反馈配对在本次 visual_only 中正常，不据此开底盘。

乙抽看两路首/中/尾、弯道与纠正处，检查来源、模糊和缺帧；软件时间配对不保证曝光同步。C 使用 EXPORT_PATH 为图像根、camera_frames.jsonl 为清单，`--dataset-role visual_sequence`（不是 static）。公共清单可能省略未知源时钟/接收时钟碰撞帧，查 public_omissions，不能把清单数当原始全量数。完整数据仓库外保存，交总控安排传输，不提交原图到 Git。

**异常分支：** 若 capture 非零、complete=false 或缺必要文件，保留 SESSION_PATH 与 RUN_DIR/capture.log，不执行或反复重试正常 export。会话具备 manifest/frozen_config 时，只读运行：

```bash
"$PYTHON_BIN" -B -m competition.data_tools inspect --session "$SESSION_PATH" --report "$RUN_DIR/failure_inspect.json"
```

诊断退出非零是预期，查看错误/计数；若初始化失败连配置/manifest都不完整，inspect 也可能无法生成报告，此时保留日志和现有文件交 A/B 定位。不要手改 complete、删除原始内容、重用目录或放宽容差。所有报告都独占创建，重复诊断另取新文件名。

## 本轮核验与真实缺口

- 只读核对 core.validate_config、SessionWriter.status、ROS 关闭分支和五个子命令 --help，参数与本卡一致；该角色组合无需代码修复。
- 在临时配置上直接向存储核心输入两路合成图像：组合字段原样写入 manifest，无反馈 ready=true；实际运行 export、原始 inspect、派生 inspect 均退出0，2张图像可回读，示范样本0、三类标签全空。临时证据为仓库本地 `tmp/bjoy_65veclti/CHECK.json`，不是现场数据，也不作为克隆依赖。synthetic CLI 有意只接受 role=synthetic，因此本次组合通过核心合成消息验证，没有谎称运行了 ROS start。
- 仍需 A 在现场确认两路真实来源/时钟、当前部署依赖，以及 ROS 入口实际吞吐与关闭；有用短段采集时随采随查，不另设静止时长验收。本轮无 ROS 传输、无真实相机/底盘、无速度发布、无训练、无全量测试重跑、无生产代码或 Git 修改。
