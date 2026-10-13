# mission：离线任务证据验证器

纯标准库 Python；公共接口 `deepbot.offline/0.1.0` 保持冻结，模块内事件/意图版本为 `deepbot.mission/0.1.0`。没有 ROS、SSH、相机、串口、网络或电机入口。

已实现：两圈有序证据、三桶交错侧别校验、逆时针完整环岛证据、S 弯、横道连续实测停车至少 3 秒、可观察提示请求/确认、持续等杆、圈数去重、第二圈倒库证据管理、可审计 CLI 回放。

**所有 `state_event.stop_required` 恒为 `true`，所有 `motion_request` 恒为零速 `stop`。这是离线任务验证器，不能直接接上让车完成路线。** `task_intent` 给出当前语义任务、证据阻碍和执行缺口，`motion_authorized` 恒为 `false`。轨迹规划、路段闭环、倒库控制、实时高级证据产生器仍需开发。

在仓库根目录执行：

```powershell
python -B -m unittest discover -s competition/tests/mission -p 'test_*.py' -v
python -B -m competition.mission.replay demo --out competition/mission/artifacts/my_new_synthetic_run
```

测试应全部通过。demo 的两条完整合成序列应 `complete/2`；永不抬杆应 `wait_barrier/0`；漏桶和不足 3 秒应 `fault/0`；两圈未倒库应 `find_garage/2`。输出目录已存在则拒绝覆盖，请使用新目录名。

详细交接见 [HANDOFF.md](HANDOFF.md)，事件定义见 [EVENT_PROTOCOL.md](EVENT_PROTOCOL.md)。本次最终验收入口和哈希见 HANDOFF 与 `PROVENANCE.json`。
