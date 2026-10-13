# mission 内部事件与适配说明 v0.1.0

这份协议只存在于 D 的目录，不扩充公共 schema。`core.Mission.step(record, now_ns=None)` 是确定性解释器；`now_ns` 为同域接收单调时间，省略时取记录封套时间。没有隐式系统时钟，也没有按秒自动走路。每条输入返回一个审计对象、公共 `state_event` 与公共零速 `motion_request`。

## 输入封套

每个内部事件必须恰好包含下列字段；未知/缺失字段、错误类型、NaN/Infinity 速度、来源回退、时间回退、混会话/时钟均拒绝。CLI 用公共严格 JSON loader 拒绝重复键及非有限数。

```json
{
  "mission_version": "deepbot.mission/0.1.0",
  "session_id": "synthetic-example",
  "clock_id": "synthetic-monotonic",
  "source": "task",
  "seq": 10,
  "stamp_ns": 2000000000,
  "basis_stamp_ns": 2000000000,
  "event_id": "synthetic-example/task/10",
  "evidence_role": "synthetic",
  "name": "marker",
  "lap": 1,
  "evidence_refs": ["synthetic-example/marker-crossing/1"],
  "data": {"number": 1, "direction": "forward", "rearmed": true}
}
```

`stamp_ns` 是事件生成时刻，`basis_stamp_ns` 是其最旧必需输入接收时刻，两者与 now 同域，要求 `basis ≤ stamp ≤ now` 且输入未过期。不是填当前处理时间来刷新旧证据。`seq` 每 source 严格递增，event_id 按 source 去重。相同身份且内容完全相同的即时重发不推进，返回 `duplicate_ignored` 并保守重置横道计时/抬杆确认；更改内容复用身份、换新 ID 重复已完成任务或过期重发均拒绝。任务观测引用不能在后续任务中重复使用，避免一帧证明多次过线。反馈、路面和横杆来源会话内固定，不能改 source 绕过旧帧/来源时钟检查。

`evidence_role` 可为 synthetic 或 recorded_evidence，必须等于配置值。后者只是离线记录标签，**没有自动证明真实性、来源可信度或自主成功**。`lap` 指事件属于第几圈 1/2；公共 `lap_completed` 指已完成 0/1/2。

## 事件 data：字段必须完整且不多填

| name | data 字段/条件 | 进入或退出约束 |
|---|---|---|
| start | `{}` | standby → exit_garage |
| garage_exit | fully_out=true | 实际出库证据后 → road |
| marker | number=1..8，direction=forward，rearmed=true | 数字严格依序；5 前必须三桶；7 前完整出环岛；8 前完成 S 弯 |
| cone_pass | index=1..3，cone_id 非空，side=left/right，clearance_confirmed=true | 标记 3 已过、5 未过；同圈三个不同桶；侧别必须匹配配置，marker4 可与桶事件交错 |
| roundabout_enter | entry_confirmed=true | marker6 后进入 |
| roundabout_orbit | direction=ccw，swept_rad≥2π，loop_closure=true，path_around_island=true | 已进入；仅累计旋转不够，还要绕岛路径与闭合证据 |
| roundabout_exit | exit_confirmed=true | 完整 orbit 后退出 |
| s_enter | `{}` | 此合成拓扑固定在 marker7—8 之间 |
| s_exit | continuous_path_confirmed=true | 已进入 S 弯 |
| crosswalk_arrive | before_line=true | marker8 后，尚未压横道；清空此前停车时间，创建提示请求 |
| notice_ack | request_id 匹配，channel=speech/display，observable=true | 本次横道停等中；请求存在不等于实际已播报/显示 |
| crosswalk_depart | crossing_confirmed=true | 连续实测静止≥3秒、提示已确认、反馈/道路新鲜、横杆持续确认 clear 后才接受 |
| lap_end | forward_crossing=true，rearmed=true | 已过横道才计圈；第一圈回 road；第二圈进 find_garage |
| garage_found | entry_geometry_confirmed=true | 两圈结束后的真实库口几何证据 |
| garage_aligned | alignment_confirmed=true，rear_clearance_confirmed=true | align_garage → reverse_parking |
| parking_complete | front_wheels_inside=true，no_board_contact=true，geometry_confirmed=true | reverse_parking 后有负向实测反馈，再有当前静止反馈和几何完成证据；才 complete |
| tick | `{}` | 只刷新新鲜性与输出；不能增加实测停车时长 |
| feedback | vx_mps、vy_mps、wz_radps（有限数），source_stamp_ns（正整数）、source_clock_id（非 unknown） | 来自实测反馈；源时钟固定递增，basis 也严格递增 |
| road | frame_seq（非负整数），valid（bool） | 帧序号及帧 basis 严格递增；valid=false 阻碍路段证据/横道通行 |
| barrier | frame_seq，value=down/clear/unknown，observed（bool） | clear/down 必须 observed=true；未知/空帧不放行；帧序号及 basis 严格递增 |

left/right 指沿规定行进方向，车辆从桶的哪侧绕过，不是框在图像哪边。现场左右顺序、S 弯与标记点拓扑尚未确认；示例 L/R/L 与 S 在 7—8 是**合成假设**。当前代码仍需按实际路线证据复核/必要时改造拓扑，不仅是改一组秒数。

所有任务证据还要求新鲜实测反馈和有效道路。传感器事件不自动生成 marker、cone_pass、orbit、parking_complete 等高级事件；布尔字段是外部待实现证据判定器的断言，核心不能验证断言真假。

## 停车与横杆

示例参数：反馈连续间隔严格小于 150ms，输入 TTL=250ms；平移各轴绝对值≤0.005m/s、旋转≤0.01rad/s 视为测量静止。它们只用于合成验收，**未按真车噪声/延迟/蠕动校准**。

到达横道后第一条合格静止反馈开启计时，起点不得早于进入横道状态的时间。只计算两条有效实测反馈间被连续覆盖的区间；tick 不给最后一帧续时。反馈丢失或任一轴移动重置；恢复后重新计满 3 秒。反馈源时间缺失/重放/重置是故障。采样之间仍可能发生未观测运动，因此还需验证频率、测量真实性和外部轮胎证据。

横杆至少 3 个递增独立帧、持续跨度至少 200ms 才建立 clear 资格；down/unknown/过期清空资格，空检测必须 unknown。资格是历史连续观测形成的状态，持续依赖最新帧新鲜性；它不是仅看到一次 clear 就走。横杆重新落下或道路/反馈失效时撤销尚未执行的过横道条件，重新取得停车证据。合法长等待没有 1.2s/任意总等待时间的自动失败门槛。

## 公共传感器 adapter

可直接给 `step` 输入公共 motion_feedback、road、detections；逐记录先调用冻结 `validate`，再适配为内部事件：

- feedback 保留 source_topic 作为来源的一部分，必须有源时间；不把源时钟与本机接收钟相减。
- road/detections 的 basis 保留原 `frame_stamp_ns`，绝不使用重发封套时间；新 seq 携带相同帧也被拒绝。
- road 默认配置 low、barrier 默认 high；仅消费明确配置的相机角色，不融合任意来路。角色不等于前/后摄像头。
- detections.objects=[] + unknown 可正常输入；空结果 + clear/down 会被公共验证器拒绝并停车故障。
- adapter 当前只做单记录/相邻流检查。未加载 camera_frame 数据库，不证明图像存在、来源物理身份、标注真实或帧链完整；A/B 必须先做会话/帧引用验证。混合流需要上游路由，不能把 camera_frame 或别的 kind 直接扔给此核心。

## 输出与 TTL

审计对象含 accepted/reason、transition.exit/enter、当前 state、lap_completed、实际累计 dwell_ns、新增有序 ledger、notice_request、task_intent 和两种公共记录。任务意图如 follow_road、alternating_cones_required、ccw_full_orbit_required、hold_for_barrier、reverse_required 只描述待做任务；execution_blockers 始终声明控制适配缺失和离线无运动授权。

`state_event.stop_required=true`；`motion_request.mode=stop` 且速度全零。请求 basis 取当前所需反馈、道路以及横道期间横杆的最旧接收时间，并纳入本次事件 basis；重发 tick 不抬高旧反馈/图像的 basis。历史路段完成、停车连续区间、clear 资格属于持久任务证据，不作为“当前帧”续命。请求可能故意已过期；接收端应按 A 的规则“缺失或过期请求默认停”，不得靠过期 stop 主动覆盖一条仍生效 drive。最终控制仲裁尚未实现。

格式/顺序/任务条件错误会锁存 fault，无自动复位。相同即时重发只保守 hold，不能重复计圈或 complete。complete 在该离线状态机中必须有完整两圈 ledger、逆向实测反馈及停车几何断言；`autonomous_success` 永远 false。
