# D 交接：任务状态机与离线验收

日期：2026-10-13。范围只涉及 `competition/mission` 与 `competition/tests/mission`。未 SSH、未接设备、未运行历史 live 测试、未发真实速度、未创建其他聊天/代理、未执行任何 Git 写入或分支操作。

## 结论与版本

已经交付可运行的纯 Python 类状态机和 CLI 回放器，不是占位 README。它验证外部证据的顺序、完整性、时间/去重约束，并产生状态日志和任务意图。**`state_event.stop_required` 恒 true、`motion_request` 恒 stop，它是离线任务验证器，不是能直接驱动车辆完成两圈的任务控制器。** 真车两圈自主能力没有被本次工作证明。

公共接口仍为 `deepbot.offline/0.1.0`，未修改 CONTRACT/schema/examples。内部事件和任务意图为 `deepbot.mission/0.1.0`。开始检查时目录为本仓库，分支 master，HEAD 未出生，代码 uncommitted；按照本轮协调指令在独占目录开发，不将旧“必须先提交”作为阻断。最终文件 SHA-256、所依赖公共接口哈希、解释器与 Git 只读快照见 `PROVENANCE.json`。没有伪造 commit。

收尾只读复核时，共享仓库已有基线 `7b5315d619c7bca37948f63bdf69a04b8806cc5b`（由其他工作过程建立，D 未执行 Git 写入）；本模块 README 为修改状态，其余交付仍未跟踪/未提交。该基线哈希不是本轮 mission 成果的提交号，应按 PROVENANCE 的逐文件哈希验收。

## 具体改动

| 文件 | 已实现内容 |
|---|---|
| `__init__.py` | 内部版本，无导入副作用 |
| `core.py` | Config、Mission.step、snapshot；有序圈/任务 ledger、去重/防旧帧、停车连续计时、等杆、故障锁存；公共传感器 adapter；公共零速输出及独立任务意图 |
| `synthetic.py` | 与状态机状态独立的假事件生成器；两种落杆圈次、持续等待、漏项等序列 |
| `replay.py` | 严格 JSONL CLI；拒绝覆盖；输入行哈希、审计 JSONL、公共 JSONL、摘要/代码哈希 |
| `EVENT_PROTOCOL.md` | 每种高级事件的精确内部字段、时钟/去重/TTL 与适配边界 |
| `README.md` / 本文 | 使用入口、验收证据和交接缺口 |
| `competition/tests/mission/test_mission.py` | 独立离线单元/集成测试；不触达 reference 里的 live 工具 |

## 复现命令与结果

从 `C:\Users\hongs\Documents\ChatGPT\智能驾驶赛` 执行，均仅使用标准库：

```powershell
python -B -m unittest discover -s competition/tests/mission -p 'test_*.py' -v
python -B -m competition.mission.replay demo --out competition/mission/artifacts/my_new_synthetic_run
python -B -m competition.mission.replay run competition/mission/artifacts/synthetic_20261013_final/complete_down_first.input.jsonl --config competition/mission/artifacts/synthetic_20261013_final/config.json --session synthetic-down-lap-1 --clock synthetic-monotonic --out competition/mission/artifacts/my_new_replay
python -B -m competition.interfaces.validate competition/mission/artifacts/synthetic_20261013_final/complete_down_first/public.jsonl
```

第一条应所有测试通过；第二条生成六条演示；第三条重放第一圈落杆完整序列并输出 `complete/2`；第四条验证公共输出形状、时序与唯一 ID。新输出目录已存在会拒绝覆盖，换新的目录名即可。run 在锁存 fault 时退出码 2；没有 fault 返回 0 **不代表 complete**，合法永远等待同样返回 0，应检查 summary.state。demo 故意包含 fault 拒绝案例，输出码 0 只代表演示生成成功。

最终验收：`artifacts/tests_20261013.txt`、`artifacts/synthetic_20261013_final/index.json`、每场景 `audit.jsonl/public.jsonl/summary.json`、`artifacts/contract_validation_20261013.txt`。早期 `synthetic_20261013_01` 为修订前探索回放，最终以 `synthetic_20261013_final` 及 PROVENANCE 为准。

实际结果：**32 项测试全部通过**（12.829s）。两种完整合成回放各 447 条输入、0 拒绝；永不抬杆 2030 条输入保持 wait_barrier；漏桶/短停分别 28/114 条输入并各拒绝 1 条；两圈未倒库 444 条输入保持 find_garage。六份 public.jsonl 共 **7020 条公共记录**均通过冻结 `validate_stream`。这些是离线逻辑结果，不是实车成绩。

| 合成场景 | 预期最终结果 | 含义 |
|---|---|---|
| complete_down_first | complete，已完成 2 圈，0 拒绝 | 第一圈落杆，确认抬起后继续，最后有倒库证据 |
| complete_down_second | complete，已完成 2 圈，0 拒绝 | 第二圈落杆，不能仅靠 3 秒放行 |
| never_raised | wait_barrier，0 圈，0 拒绝 | 650 次 100ms 更新，超过 65 秒等待不被误杀 |
| reject_skip_cones | fault，0 圈 | 第 5 标记前缺三个绕桶证据 |
| reject_short_stop | fault，0 圈 | 不足 3 秒就声称越过横道被拒绝 |
| no_parking_no_complete | find_garage，2 圈 | 两圈不等于任务完成 |

测试另外覆盖：未知/抖动横杆，单次 clear 不足，空检测 clear、过期数据、源时钟重放、相同帧换新封套；三轴任一移动重置停车、反馈断档、tick 不增加停稳时长、横道到达前的静止不计入；旧依据的 TTL 不随重发刷新；漏环岛/S弯、错误桶侧别、重复桶、未闭合绕岛、标记/圈数去重、任务引用复用、第一圈误入库、缺后方净空、没倒车/没停稳/前轮未入库；重复完成不二次计数；严格 JSON、故障锁存及拒绝覆盖输出。

合成 profile：桶顺序 L/R/L、S 位于 7—8；**不是实测赛道配置**。参数 250ms TTL、150ms 反馈间隔、静止噪声门限及 200ms 抬杆确认跨度也未经现场验收。全部 summary 写 `autonomous_success=false`、`hardware_access=none`。

## A/C 需要开发的真实事件来源

当前 C 的 road/detections 不能证明下列事实；adapter 没有偷偷把框转换成完成事件。

| 事件/证据 | 后续产生方与代码缺口 | 必需现场依据 |
|---|---|---|
| start / garage_exit | A 会话初始化与定位/出库边界适配；需要整车通过判定器 | 起点、出库方向、轮胎边界 |
| marker / lap_end | C+A 时序地标跟踪、离开后重接近/方向/拓扑判定器；独立任务 ID 与 evidence refs | 正式标记可见性、圈线位置、防同帧抖动验证 |
| cone_pass | C 目标身份跟踪 + A 几何/路径进展适配；不能用检测帧数充当经过三个桶 | 官方交错侧别、车轮外廓、道宽、最小净空 |
| roundabout_enter/orbit/exit | C 分叉/入口出口判定，A 正确 yaw 展开/路径闭合与绕岛验证代码 | 岛的空间关系和完整轨迹；仅原地旋转 2π 不够 |
| s_enter/s_exit | C+A 曲线段定位、完整连续路径进展适配；核实当前合成拓扑是否匹配实际 | S 前后锚点、道路边界 |
| crosswalk_arrive | C 横道边缘和车辆/轮胎停车点几何，A 制动/位置判定 | 轮胎未压线、延迟、停止距离 |
| feedback | A 实测反馈源适配/质量监控，源时钟/符号/噪声校准；丢包不得复用值 | 真实速度与轮胎静止外部对照 |
| barrier | C 同帧横杆状态证据、遮挡/抖动/未检出处理；A 校核可通行净空，不仅抬杆视觉类别 | 落杆、抬杆、运动中、空检测、未知样例 |
| notice_ack | A 新增可观察显示或语音执行器及执行回执；本模块只有请求与 ACK 管理 | 裁判视角可读/可听证据 |
| garage_found / aligned | C 库口/挡板位姿估计，A 对准目标适配和误差边界；不能把 garage_entry 框当姿态 | 内参/安装姿态、车宽、库宽/深度 |
| rear_clearance | C/A 后向视野或合规测量链、后方占用及碰撞裕量计算 | high/low 不等于前/后，相机实际视野待验 |
| parking_complete | A+C 前轮接地点过线几何与挡板无接触判定；已有负 vx+静止只是必要条件 | 外部全场/轮胎证据与实际倒车过程 |

真实高级事件产生器必须把可回查原始记录引用送入 ledger，并正确保留最旧输入时间；当前库只验证字段和事件顺序，不能鉴别伪造的布尔断言。B/A 还需在进入本适配器前完成会话、camera_frame 与原图引用的完整性检查。

## 倒库及运动执行仍缺哪些代码

已实现两圈后找库、对准、倒车阶段的任务管理；拒绝第一圈入库；记录后方净空断言；必须在 reverse_parking 阶段观察到负向实测 vx，随后当前静止且前轮入库/无碰板/几何完成断言齐备才 complete。

尚未实现库口位姿求解、后方盲区处理、碰撞检测、可行倒车轨迹、轨迹跟踪、误差修正/恢复，也没有路段循迹/交错绕桶/绕岛的目标或轨迹请求适配。这里没有用固定速度×秒数编造路线。A 后续需设计内部 task_intent → 路段目标/轨迹 → 唯一速度仲裁的接口，并由 C/A 实现上述证据产生器、显示执行器和控制闭环；然后才能进入分项/真实验证。**剩余工作包含明确的软件开发，不能概括为“只差实车测试”。**

公共 v0.1.0 没有上述高级任务事件、几何置信边界、显示请求/回执、轨迹目标字段。提请 A 审查 EVENT_PROTOCOL 后决定新增公共版本或保留独立适配层；D 本轮没有改变公共枚举/字段。不要把 `passage_evidence_ready` 或 task_intent 当最终运动授权，所有执行阻碍和全局保护仍由 A 仲裁。
