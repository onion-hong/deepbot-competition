# 双相机数据：采集、回读、共享

更新：2026-10-13。配合[团队路线](TEAM_GUIDE.md)使用。这里提供现有 CLI 的操作流程；**真实 ROS 采集入口仍待现场验收**，当前不据此恢复车辆运动。设备接入和部署统一由甲/A 负责，乙管数据，丙接离线回放。

## 先区分这次采的是什么

| 用途 | 配置 | 允许怎样解释 |
|---|---|---|
| 静态取景/手推视觉 | `mode=visual_only`，`role=manual_visual`，method 为 `stationary` 或 `hand_push` | 反馈可以空；只用于视觉和诊断，不能冒充驾驶动作标签。手推仍需以后有移动采集条件 |
| 手柄示范 | `mode=demonstration`，`role=manual_demonstration`，method 为 `joystick` | 必须有有效反馈；反馈不等于手柄命令或人的意图。当前先不进行 |
| 自主验证 | `role=autonomous_evaluation`，method 为 `autonomous` | 单独保留完整自主过程、失败和接管；不能当手柄示范，本工具不判自主成功 |
| 合成软件检查 | `role=synthetic`，method 为 `synthetic` | 仅工程测试，不是现场训练或比赛证据 |

一次会话从创建起固定 `session_id` 和 `split=development/validation`。同一会话的相邻帧、两路相机、所有派生图像都属于同一组。开发中看过并用于调参的验证会话要在外部台账标记 consumed；之后另采未用于修改方案的验证会话，不随机把相邻帧分进两组。

## 本地目录和现场配置

代码留在 Git，完整数据放仓库外。下面是建议的数据目录，尖括号表示实际新编号，不是待提交到 Git 的目录：

```text
<DATA_ROOT>/
  raw/<SESSION>/                    原始会话，关闭后只读
  derived/<SESSION>/<EXPORT_ID>/    导出包，独立批次
  replay/<SESSION>/<REPLAY_ID>/     C 的叠加图与诊断
  reports/                         质检报告与人工复核结论
  catalog/sessions.jsonl            队内维护的会话台账
```

台账每条至少写 session_id、split、role/method、配置哈希、源码/实际 Git 版本、场景、原始/派生的**相对路径**、质量/完整性结论、是否用于调参、未覆盖项。记录器 manifest 的 code_commit 可能是 null，它仍提供代码文件哈希；另记本次部署的实际 Git 提交，不把 null 改成猜测的版本。台账与新报告写在会话外，不能改冻结原始 manifest 破坏哈希。

现场配置从[静态配置候选](../../data_tools/vehicle.visual.example.json)准备成仓库外的本机 JSON，由甲核对后使用。候选来自一次历史观察，**不是当前设备在线的证明**。必须核对：

- 两路 physical_id、稳定 USB 路径、实际 topic/type，以及相机对应的安装位置。high/low 只是高低安装角色，不等于前后；不能用易变的 video 编号、重复序列号或相同 frame_id 作为唯一身份。
- 来源时钟是否已知，是否确实可以同当前 ROS 时钟比较；未知填 unknown 并明确选择接收时间近似，不能为了通过而改成一个编造域。
- 解码尺寸、清晰度、姿态和方向；源 header 是软件采样时间，不是曝光同步证据。历史空 format、同 frame_id、空 CameraInfo 不能单独否定可解码图像，尺寸从图像取得。
- `visual_only/manual_visual/stationary`、两相机、feedback=null、command=null、split、数据根、磁盘余量。不要为了有反馈就开启底盘。
- max_age、启动宽限和配对容差。候选值只用于工程短录；正式容差要冻结并记录，不静默放宽。核实身份后才设置 identity_verified=true。

原始格式、事件和标签细节见 [SCHEMA.md](../../data_tools/SCHEMA.md)。synthetic 配置内的测试话题完全是虚构的，不能替代真实映射。

## 下一次静止 20 秒：四步卡

**执行者：甲/A；环境：车载 Bash，已加载正确 ROS 1 环境，车辆保持静止，两路相机已由现场负责人确认运行。** 本卡不启动 master、相机、串口或底盘。若设备不在线，停止在准备阶段，不能擅自追加重启或运动操作。

先由甲填写并导出变量：`REPO_ROOT` 为部署仓库路径，`DATA_ROOT` 为仓库外数据根，`SITE_CONFIG` 为已核对配置，`ROS_MASTER_URI` 为当前已有 master 地址；不要把实际地址或连接凭据写进公有文档。

```bash
: "${REPO_ROOT:?填写实际部署根目录}"
: "${DATA_ROOT:?填写仓库外数据根目录}"
: "${SITE_CONFIG:?填写已核对的现场JSON路径}"
: "${ROS_MASTER_URI:?核对已有ROS环境，不在这里启动master}"
cd "$REPO_ROOT"
python3 -c 'import sys, PIL, rospy; from sensor_msgs.msg import CompressedImage; print(sys.executable, PIL.__version__)'
export SESSION="static_$(date +%Y%m%d_%H%M%S)_$(python3 -c 'import uuid; print(uuid.uuid4().hex[:8])')"
export SESSION_PATH="$DATA_ROOT/raw/$SESSION"
printf 'SESSION_PATH=%s\n' "$SESSION_PATH"
```

依赖检查应打印实际解释器和 Pillow 版本，失败表示先补环境；不要假定普通虚拟环境能导入车载 rospy。ROS 入口另需 `nav_msgs`、`geometry_msgs` 标准消息，即使这次未配置反馈。配置含凭据或个人信息时先由甲清理配置内容，不要把这些内容传给记录器存入 frozen_config。

**1．开始记录（车载、待验收）：**

```bash
python3 -B -m competition.data_tools start --backend ros --config "$SITE_CONFIG" --root "$DATA_ROOT/raw" --session "$SESSION" --seconds 20
```

预期打印 SESSION、新会话路径和两路各自计数/新鲜度/ready。无反馈也应能在 visual_only 模式就绪；ready 不代表可以行车。输出已存在、重复身份/话题、master不可用、缺流、坏图或写盘错误都应报告，保留失败会话。不要删除目录后用同名重来。

**2．保持停车后结束（车载、待验收）：** 20 秒到期通常自动关闭。检查 CLOSED 和 manifest.complete=true；只看到 CLOSED 字样不足以确认成功。如需提前结束，在第二个已配置环境的终端填**同一个** SESSION_PATH 后执行：

```bash
: "${SESSION_PATH:?填写第一终端打印的准确会话路径}"
python3 -B -m competition.data_tools stop --session "$SESSION_PATH"
```

stop 仅请求结束记录，不负责停车。已经关闭的会话无需再 stop；重复执行会拒绝。异常退出、未完成、关闭失败的数据原样保存，不能手工把 complete 改成 true。

**3．离线导出（车载或装好 Pillow 的本地电脑）：** 从该电脑的仓库根目录运行，DATA_ROOT 指向这台电脑的数据副本；不要沿用别人电脑的路径。这里沿用第一终端的 SESSION；换电脑后按实际会话名填写。

```bash
EXPORT_ID="export_$(python3 -c 'import uuid; print(uuid.uuid4().hex[:8])')"
export EXPORT_PATH="$DATA_ROOT/derived/$SESSION/$EXPORT_ID"
python3 -B -m competition.data_tools export --session "$DATA_ROOT/raw/$SESSION" --output "$EXPORT_PATH"
```

预期产生两路图像、samples、pair_audit、camera_pairs、events、quality 和派生 manifest。visual_only 的反馈/命令/人的意图为空、示范样本0是正常结果。不完整/哈希错/不明确的纠正事件会拒绝导出；时间错配要查原因，不改容差让数字变好。

**4．回读质检（同一台电脑、仓库根目录）：**

```bash
mkdir -p "$DATA_ROOT/reports"
REPORT_ID="$(python3 -c 'import uuid; print(uuid.uuid4().hex[:8])')"
python3 -B -m competition.data_tools inspect --session "$DATA_ROOT/raw/$SESSION" --report "$DATA_ROOT/reports/${SESSION}_${REPORT_ID}_raw.json"
python3 -B -m competition.data_tools inspect --export "$EXPORT_PATH" --report "$DATA_ROOT/reports/${SESSION}_${REPORT_ID}_export.json"
```

预期两路所有图像可解码，计数/文件哈希一致，退出码0。失败退出非零并保留报告；所有报告也使用新文件名。分别看 integrity_ok、quality_ok、physical_identity_verified，不用一个“通过”概括文件、配对、实物身份与任务能力。乙再查看两路首/中/尾及异常段，核对视野不是同一相机写两份；静态同景字节相同只是可疑证据。

如果 Windows PowerShell 上离线处理，将已经核实的 Python 解释器记作 `$py`，路径记作 `$sessionPath`、`$exportPath`、`$reportPath`，使用同一 CLI，例如：

```powershell
& $py -B -m competition.data_tools export --session $sessionPath --output $exportPath
& $py -B -m competition.data_tools inspect --export $exportPath --report $reportPath
```

这里的变量必须填写当前电脑真实值；`$exportPath`、`$reportPath` 必须未使用。不要复制旧 HANDOFF 的个人解释器路径。

## 交给丙回放，并决定下一批拍什么

静态导出通过后，在本地仓库根目录用安装了 NumPy/Pillow 的解释器执行：

```bash
REPLAY_ID="replay_$(python3 -c 'import uuid; print(uuid.uuid4().hex[:8])')"
python3 -B -m competition.perception.replay --root "$EXPORT_PATH" --manifest "$EXPORT_PATH/camera_frames.jsonl" --dataset-role static --output "$DATA_ROOT/replay/$SESSION/$REPLAY_ID"
```

这是实际存在的 C 清单入口。图像路径相对导出包根目录，不能只发送 JSONL 而遗漏 images。查看 overlays、diagnostics、provenance、summary：CLI 退出0只表示输入遍历无拒绝，所有道路输出无效仍可能退出0；要看原因和画面。道路像素有效也不证明净空或行车许可。

B 可能因未知来源时钟或接收时钟分辨率碰撞，在公共 camera_frames 清单省略帧；raw/samples 仍完整，数量与原因见 public_omissions。不能伪造递增时间来隐藏省略，也不能把该清单当原始全量帧数。

先覆盖直道偏位、左右弯/S弯、分叉、环岛入口/出口、桶及相似蓝背景、人行道/横杆落下抬起运动未知、车库口与倒车视野，以及阴影/反光/褶皱。看过静态结果再调整视野和采集清单，不立即录大量同样不可用的图。后续移动/手柄采集须恢复现场条件，反馈与标签语义须先核实。

## 纠正和失败必须留在原始记录里

停止、等待、倒车、纯横移都不能被运动阈值过滤掉。实测 angular.z 是角速度，通常 rad/s，不是手柄转角或控制指令；观测命令也不自动等于人的意图，缺失标签写 null。

未来记录期间，乙可在记录终端环境发送纠正区间：

```bash
python3 -B -m competition.data_tools event --session "$SESSION_PATH" --type correction --phase start --interval-id correction01 --reason 'manual correction begins'
python3 -B -m competition.data_tools event --session "$SESSION_PATH" --type correction --phase end --interval-id correction01 --reason 'manual correction ends'
```

应看到 EVENT_REQUESTED，并在 events.jsonl 查对应 request_id 已被接收。事件时刻是记录器处理请求时刻，不是假装精确动作时间；用全场录像辅助复核。派生示范按 [start,end) 排除图像或配对反馈处于纠正段的样本，原始文件不删。未闭合 start 保守排除后续，孤立 end/不匹配区间须复核；本版没有事后直接修改冻结事件的 CLI。

## 数据怎么归档、发给队友

完整图像、录像、raw 消息、派生图像和模型不进 Git。队内通过单独的数据盘或受控共享空间传输，分享渠道不写在公有仓库里。保留失败会话，原件只读；备份和重新导出都使用新位置。

乙为每次共享创建一个**新的包目录**，复制完整原始会话、对应导出包、质量报告，必要时加录像/摆位图和台账摘录。保留包内目录层级，建议：

```text
bundle_<SESSION>/
  raw/<SESSION>/...
  derived/<SESSION>/<EXPORT_ID>/...
  reports/...
  HANDOVER.json
```

HANDOVER.json 手工填写 session_id、split/role、代码提交或源码哈希、配置哈希、包内相对路径、质量结论、consumed 状态、数据用途和缺项。不要填姓名、账号、连接地址或凭据。分享原始数据前核查 frozen_config/元数据和画面；需要公开示例时另做脱敏派生版本，不能私自改原始文件后仍声称原哈希有效。

下面是本地 **Bash 打包范例**，用 Python 标准库即可；先把 BUNDLE_DIR 设为刚准备好的包目录，ARCHIVE_PATH 设为包目录外、尚不存在的 zip 文件路径。它保存文件相对路径、大小和 SHA-256 清单，并生成整个压缩包的哈希；不删除或覆盖原数据。本轮只核对脚本语法，没有对现场数据执行打包。

```bash
: "${BUNDLE_DIR:?填写新包目录}"
: "${ARCHIVE_PATH:?填写包目录外的新zip路径}"
export BUNDLE_DIR ARCHIVE_PATH
python3 - <<'PY'
import hashlib, json, os, zipfile
from pathlib import Path
root = Path(os.environ['BUNDLE_DIR']).resolve()
archive = Path(os.environ['ARCHIVE_PATH']).resolve()
sidecar = Path(str(archive) + '.sha256')
if not root.is_dir() or archive == root or root in archive.parents:
    raise ValueError('archive must be outside an existing bundle directory')
if archive.exists() or sidecar.exists():
    raise FileExistsError('use new archive and checksum names')
def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()
files = sorted(p for p in root.rglob('*') if p.is_file())
if any(p.is_symlink() for p in root.rglob('*')):
    raise ValueError('bundle must contain regular copied files, not links')
index = [{'path': p.relative_to(root).as_posix(), 'bytes': p.stat().st_size,
          'sha256': digest(p)} for p in files]
with (root / 'FILE_HASHES.json').open('x', encoding='utf-8') as f:
    json.dump(index, f, ensure_ascii=False, indent=2)
with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as z:
    for p in files + [root / 'FILE_HASHES.json']:
        z.write(p, p.relative_to(root).as_posix())
with zipfile.ZipFile(archive) as z:
    if z.testzip() is not None:
        raise ValueError('archive CRC check failed; retain it for diagnosis')
with sidecar.open('x', encoding='utf-8') as f:
    f.write(digest(archive) + '  ' + archive.name + '\n')
print('ARCHIVE_READY', archive.name, 'files=', len(index) + 1)
PY
```

接收者先比对压缩包 SHA-256，再解压到新目录，按 FILE_HASHES.json 逐文件核对相对路径、大小和哈希；不要只看 ZIP 能打开。再用本页 inspect 命令检查 raw 和 derived，验证两路图像及数据分组；自己电脑上的绝对路径与发送者不同不影响相对引用。接收者将“收到/哈希一致/回读结论”写入包外台账，完整数据包仍不提交 Git。

目前尚缺可用真实双路短录、全场录像/摆位、真实反馈标定和命令可见性、正式连续路段及独立验证会话。仓库里的合成夹具可重建，不应被当成这些外部数据的替代品。
