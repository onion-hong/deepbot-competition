# B 存储格式 deepbot.data/0.1.0

这是一套 B 模块内部磁盘格式；没有修改 `competition/interfaces` 中 A 的 `deepbot.offline/0.1.0`。本版本用于工程验证，尚未通过现场双相机传输验收。所有时间为整数 ns，原始异常值保留。

## 配置

必需字段见 `synthetic.example.json`。cameras 必须恰有 high/low，分别指定 physical_id、identity_verified、topic、message_type、source_clock_id；可保存 device_key 和身份核实依据。physical_id、已给出的 device_key 和规范化话题不得重复；ROS 适配再检查 remap 后实际话题是否相同。

high/low 不隐含前后朝向。相同序列号、相同 header.frame_id、空 CompressedImage.format 不作为重复相机判据；原 format/frame_id 保留，图像尺寸和解码编码由实际字节取得，不使用空 CameraInfo。解码结果为 RGB，不能按 OpenCV 默认 BGR 解释。

mode=visual_only 或 demonstration。role=synthetic/manual_visual/manual_demonstration/autonomous_evaluation，acquisition_method 与 role 组合校验。split=development/validation 在会话创建时固定，整个导出继承该值。synthetic 明确是工程样例，不能进入正式示范证据。validation_consumed 默认 false；一旦用于调参，由 A 的数据清单另记 consumed，不能声称一直未见。

feedback 可为 null 或指定 nav_msgs/Odometry；command 可为 null 或指定 geometry_msgs/Twist。后者仅订阅观测，不代表人的手柄意图。demonstration 缺反馈配置拒绝启动，缺反馈流不就绪；visual_only 无反馈正常记录，但 demonstration_eligible 永远 false。自主角色不生成手柄示范标签。

source_clock_id 未核实时填写 unknown。compare_source_to_ros_time=true 只能在确认 header 与本节点 ROS time 同域时使用，用来诊断旧/未来来源时间；不将 header 当曝光时刻。每一路都检查 source 重复/倒退。接收单调时钟允许相等的有限分辨率时间值，靠 seq 区分；更早值判坏。墙钟回退按流检查，正常跨流回调写入重排不误报。没有自动切换时间依据或扩大容差。

max_age_ns、startup_grace_ns、reserve_bytes、pairing.basis/tolerance_ns 必须显式给出。样例的 500ms 新鲜度、5s 启动宽限和 50ms 配对容差只是工程试采配置，不是正式赛验收标准。

## 原始会话

```text
<root>/<session_id>/                 独占新建；已存在即失败
  manifest.json                     初始 complete=false，成功关闭后才 true
  frozen_config.json                规范化后的实际配置及 SHA-256
  receipts.jsonl                    每路原始消息与来源/接收时钟/质量索引
  events.jsonl                      人工事件；不伪装 D 的 state_event
  requests/*.json                   保留的人工事件请求及请求墙钟
  STOP_RECORDING                    仅请求停记录；不控制车辆
  raw/high_000000000.bin             图像原压缩字节或原像素字节
  raw/low_000000000.bin
  raw/feedback_000000000.bin         原消息字节（ROS）或合成 JSON 字节
  raw/command_000000000.bin          若确实观测到
  raw/*.rosmsg                      ROS 完整消息序列化（ROS 入口才有）
```

manifest 记录 session_id、split、role、mode、相机映射、clock_id、开始/结束时间、counts、完整性、退出原因、错误、配置哈希、源码哈希、原始文件大小与 SHA-256。Git commit 不自动猜测：本模块新代码未提交，写 code_commit=null 和 uncommitted_or_commit_unverified；现有主仓库 HEAD 不能冒充这些文件的提交。

receipt 含 stream_id/seq、实际 topic、message_type、physical_id、来源 stamp/clock、receipt_mono_ns/receipt_unix_ns、raw_ref/sha256/size、图像 descriptor/decoded、motion、diagnostics/warnings 和 ROS 元数据。ROS 元数据保存 type/MD5/definition、header seq/frame_id、原 format、publisher callerid，.rosmsg 可按相应定义反序列化。坏图/时间异常先尽力写原始字节和诊断，再停止 ROS 采集；写盘本身失败的消息不承诺已保全，会话不完整。

事件支持 point/start/end；区间必须有 interval_id。event CLI 将请求写入新文件，由记录器接收时写 events.jsonl，事件时刻是**记录器收到请求的时刻**，不是现场动作的精密时间，也不是请求进程的 monotonic 时钟。请求尚未被确认就结束会话，回读报 unacknowledged_event_requests。重要动作可外部录像复核，不把命令发起时间冒充物理动作时间。

关闭：关闭输入门→取消订阅→等待所有已入门回调（含等待 writer 锁者）→处理事件→flush/fsync/关闭→文件清单/hash→原子替换 manifest。入门之后的消息必须在完整关闭前写完或报失败；关闭输入门之后的新回调不属于接收范围。强杀/写盘/关闭错误留下 incomplete，无“自动修复成完整”。Windows 原子替换 PermissionError 最多 5 次有限重试同一个已写临时文件，不删除文件绕过。

complete 是写入闭合标记，不代表画面有效。当前未对目录项执行额外 fsync，也未验证硬断电/文件系统断电恢复；不能承诺任意断电零损失。

## 导出

输出目录必须全新，位于外部或原会话 `derived/` 下。读取原始完整性/哈希/索引/全量解码；损坏、不完整、含不明确纠正事件的会话拒绝正式导出，但 inspect 可报告问题。导出中失败保持派生 manifest.complete=false，已有文件保留。

- `images/high|low/*.png`：可解码帧 RGB PNG。即便时间异常也保留可查看图；不可解码帧 image_ref=null，不生成假图。
- `samples.jsonl`：每个原始图像一行。session/split/camera/frame/image/raw 路径、image_valid、measured_motion、observed_command、human_intent、demonstration_eligible、training_use、exclusion_reasons。
- `pair_audit.jsonl`：每相机每帧分别对 feedback/command 配对。候选 ID、时间域、basis、tolerance、signed_delta=候选时间−图像时间、accepted、拒绝原因全部保留。即使不匹配也有一行；没有候选为 null。
- `camera_pairs.jsonl`：high 对 low 的独立软件配对诊断，不是 image-feedback 配对，也不意味着硬同步。
- `events.jsonl`：原事件原字节复制；manifest 记录事件版本 SHA-256。
- `quality.json`：分相机接收/解码/配对/排除数、全部图像分母、拒绝原因、绝对时差 p95/max、文件完整性、缺流间隔、身份未验证警告、适用范围。原始 signed delta 可在审计逐行查看。
- `manifest.json`：原会话 manifest 哈希、配对/纠正规则、派生文件哈希、complete/quality_ok。

反馈/命令最近邻按各自时钟域建立索引，同距离选择更早时间、更小 seq；abs(delta)≤容差才时间接受。没有反馈时 visual_only 的配对数=0、标签=null 是正常结果。接收配对只比较同 recorder clock_id；来源配对只比较非 unknown 同域有效 stamp。未做时间插值、执行延迟补偿或曝光同步推断。

实测字段是源 Odometry 的 linear.x/y、angular.z（通常 m/s、rad/s），不是控制命令或手柄角。源码层沿用标准 ROS 字段含义，现场符号、坐标和标定仍须 A 验证；此版本**没有将 motion 自动适配为 A 的 base_link_contract**。控制信息缺失和人的意图缺失均为 null，不补零、不拿反馈顶替。

停止/倒车/纯横移不做运动阈值过滤。correction/reposition/lift/collision/out_of_bounds/takeover 的 [start,end) 区间，若图像或选中反馈的接收时间落入其中，示范排除；原始消息与导出查看图保留。未闭合 start 排除直到会话结束；孤立 end/重复 start/不匹配类型报错。所有标签只是工程或实测运动研究用途；不能因此称学会驾驶。

## 对接 A/C

`camera_frames.jsonl` 是 adapter 生成的 A 0.1.0 camera_frame 记录，image_ref 相对**导出包根目录**，导出包是携带原 session_id/split 的独立只读派生会话。C 应同时传这个包根目录，不能把路径相对主仓库解释。

A 0.1.0 要求有来源 stamp 时 domain 不能 unknown，且同一路 receipt stamp 严格递增。因此有真实非零 stamp 但域 unknown、或接收时钟有限分辨率相等时，本适配器不伪造字段：该帧仍完整存在 raw/samples，公共交换清单省略并计入 public_omissions。其他合法帧用原值；不冒充 public motion_feedback/state_event/frame_pair。请求 A 后续决定是否升级这些约束与人工标注/运动配对格式。

正常化 PNG 采用 Pillow RGB；与 OpenCV BGR 接口对接时由消费者显式转换。原始图像尺寸来自解码结果，未标定不输出地面距离。
