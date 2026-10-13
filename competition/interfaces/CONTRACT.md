# 公共接口 deepbot.offline/0.1.0

2026-10-13 冻结，A 负责。适用于离线 JSON/JSONL，**不是已部署 ROS 消息定义**。字段形状见 `schema.json`，语义见本文，完整合成输入/输出见 `examples.jsonl`。`validate.py` 是此有限 schema 的标准库验证器，不是通用 JSON Schema 引擎。未知字段拒绝，改变字段/单位/枚举需升级版本并更新所有模块。

## 通用封套与时间

每行 UTF-8 JSON 对象（无 NaN/Infinity，无重复键），含 `schema_version`、`kind`、`session_id`、`seq`、`stamp_ns`、`clock_id`、`payload`。seq 为各 kind/来源流内非负序号；消费者使用 session+来源+seq 去重，不用检测帧数计圈。stamp_ns 是该记录生成/接收的本机单调纳秒整数；clock_id 标识唯一主机启动/回放时间域，跨 clock_id 禁止直接相减。

相机 payload 另存原始 `source_stamp_ns`（缺失/零值记 null，不能用接收时间冒充）、`source_clock_id`、`receipt_unix_ns`、`receipt_mono_ns`；封套 stamp_ns 等于接收单调时间。原始 ROS header stamp 不保证是硬件曝光时间。无 header 的数据保留 null 并显式标记来源时钟 unknown；回放不把当前播放时钟写回原采集时间。

B 配对前核实两路 source_clock_id 是否同域且时间戳有效递增；否则仅显式选择 receipt_approximate 方案，记录依据和有符号差 `low - high`。不能把不同设备时钟或墙钟和单调钟直接相减。重复/回退/旧帧原始记录保留并标坏，不能进入控制或独立训练样本。配对容差尚未经现场冻结；历史 50ms/10Hz 只是旧配置。

`frame_pair` 记录两帧序号、basis、pairing_clock_id、两路配对时间、delta_ns、tolerance_ns 和 accepted。source_header 使用同域原始来源时间；receipt_approximate 使用同域接收单调时间。accepted 只表示本次时间差在容差内，不表示图像可用、身份已由实物验证或采集验收通过。示例 50ms 仅供合成测试，现场配置仍为 null。

## B → C：camera_frame

- `camera_id` 只有 high/low，代表固定安装角色，不代表前/后。`physical_id` 是去个人信息的稳定设备键；配置保存真实 USB by-path 等映射，不能单凭 video0、相同序列号认定身份。
- `frame_seq` 在 session+camera 内递增，重新接入必须记录事件。两份相同物理流不能算双相机。
- `width_px`、`height_px` 是原始解码尺寸；`encoding` 为 bgr8/rgb8/mono8；`image_ref` 是会话根目录内相对路径，拒绝绝对路径及 `..`。JSON 不携带大图。样例图像路径是合成占位，未提供可解码图像。
- 封套相同 clock_id 的两路帧是可比较的接收时钟，不自动证明源曝光同步。

## C → D/A：road 与 detections

两类都带 `camera_id`、`frame_seq`、原始 `width_px/height_px`、`frame_stamp_ns`（对应 camera_frame 的 receipt_mono_ns）；封套为结果生成时刻，必须晚于或等于帧接收时刻。下游保留输入帧身份，不能每次重发旧结果就刷新有效期。

road：`valid`、`reason`、`quality` [0,1]、`reference_x_px`、`reference_y_px`、`target_x_px`、`offset_px`、`path_px`。原图左上为原点，x 右正、y 下正；**offset_px = target_x_px - reference_x_px**，正值表示路径在图像参考线右边，不是“车在道路右侧”，也不是米。参考线取何处由 C 明示。path_px 为原图候选路径点，未标定不报地面距离。无效时 target/offset=null、path=[]，不能复用上次道路。原厂算法内部 320×240 误差必须换算回原图；原增益不能直接应用到放大后的像素。

detections：每帧都输出 `objects`（可为空）与 `barrier_state`=down/clear/unknown。框 `bbox_xyxy_px` 为原图浮点 [x1,y1,x2,y2]，左上包含、右下不包含；0≤x1<x2≤width，0≤y1<y2≤height。缩放/letterbox 必须先逆变换。类别暂定 cone/crosswalk/barrier/garage_board/garage_entry/start_marker；这是交换词表，不是声称现有模型已支持。框的 `score` 为 [0,1]。clear 必须有同帧 barrier 证据，空结果不能表示放行；score 不是距离或可行驶判据。旧 start/crossing 的映射需 C 核实，不能直接使用旧类别下标。

## A → B/D：motion_feedback

`vx_mps` 前正、`vy_mps` 左正、`wz_radps` 俯视逆时针/左转为正；`frame_id`=base_link_contract 是离线约定坐标。`origin`=measured_odometry，保留实际 source_topic 以及原始 source_stamp_ns/source_clock_id。里程计实测 angular.z 不能叫手柄转角/控制命令；四元数 z 不能当 yaw。当前实车符号、标定、raw_odom→odom 变换待核实。超声波 Float32 的量纲未知，本版本不假造米制字段。

## D/C → A：motion_request

`source`=mission/perception（最终仲裁权在 A）；`request_id` 会话内唯一；`mode`=drive/stop；`vx_mps/vy_mps/wz_radps` 使用上述约定；`ttl_ms` 范围 1..500，`reason` 非空；`basis_stamp_ns` 是本请求依据的最旧必需输入的接收单调时刻，且必须和封套同 clock_id。有效期从 basis_stamp_ns 起算，不能重发旧感知延长时效。stop 三分量必须零。请求只写离线记录，不直接映射串口/真实 cmd_vel。

同 clock_id 且 basis_stamp_ns≤stamp_ns≤now< basis_stamp_ns+ttl_ms 才能作为未过期请求；相机新鲜性、仲裁、限幅、任务许可、反馈和现场授权还需分别检查。`request_is_current` 仅检查时间，绝不是行车放行函数。示例中正像素偏离配负 wz 仅演示原厂符号换算，不能推定所有相机姿态的控制方向。最终 A 必须唯一发布实际速度，B 不发布，C/D 不绕过。

停车保护优先；过期、丢帧、无效/未知感知保持停止。横道合法等候持续产生零速请求，停车计时从实测停稳开始，满 3 秒仍须等杆放行。不使用旧 run_factory_lap 的 1.2s 零速中止规则作为正式任务监督。现有驱动 0.5s watchdog 保留，其串口解析短包/粘包、固定 0.02s 积分和低速响应仍需专项审查，未因此获得部署许可。

## D → B/A：state_event

`event_id` 同 session 内唯一；`state` 见 schema 枚举；`lap_completed`=0..2 表示已完成圈数，不能把进行中的第二圈填 2；`segment` 为可读路段键；`reason` 非空；`evidence_refs` 为来源记录键字符串；`stop_required` 明示停止意图；`barrier_state` 同上。完成圈/倒库的证据由 D 定义并经 A 审核，事件存在不证明实车达到条件。

## 会话与磁盘格式

会话目录由 B 独占创建，存在即拒绝覆盖。raw/ 保存原始 bag/图像只读，receipts.jsonl 保留逐路时间与质量，events.jsonl 保存事件，derived/<模块>/<独立批次>/ 保存派生数据。原始完整保留停止、倒车、修正、坏帧；清洗只生成新清单。会话 manifest 至少记录 session_id、schema_version、split(development/validation)、role(synthetic/manual_visual/manual_demonstration/autonomous_evaluation)、autonomous_success、代码提交、配置哈希、相机映射、close_reason、complete、原始文件哈希。该磁盘 manifest 是 B 下一步实现要求，本版本验证器只校验七类记录，不冒称已有双路 session writer。

独立评估按整会话隔离；用于改动即标记 consumed。代码不保存绝对数据目录、操作者实名或连接密钥；本机配置另存被忽略的 `config/site.local.json`。
