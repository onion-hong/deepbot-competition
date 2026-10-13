# 文件所有权与依赖

| 负责人 | 可修改路径（均相对仓库根） | 依赖与交付 |
|---|---|---|
| A 总控/甲 | competition/platform、control、config、launch、interfaces、docs、tests/offline；根 .gitignore/.gitattributes | 维护接口、基线、最终仲裁/集成；一次合入一个模块 |
| B 数据/乙 | competition/data_tools、tests/data_tools | 读冻结接口和 reference/patched 的记录/导出；交双路离线记录/配对、质量报告、会话回读 |
| C 感知/丙 | competition/perception、tests/perception | 读 B 的帧格式和冻结接口；交 road/detections 与正式数据失败例 |
| D 任务/丙分时 | competition/mission、tests/mission | 先读合成事件和接口，后接 C；交状态机、圈数/等杆/倒库离线证据及 motion_request |

reference/**、历史原件、原始数据全部只读。模块说明、失败报告、依赖需求写在各自目录，不共同修改 docs/RESULTS.md。B/C/D 不改公共接口、底盘或最终 launch；提出变更理由和输入输出样例，由 A 冻结新版本。README 占位文件不是已实现功能。

默认串行：A 基线→B 双路离线记录→C 正式帧回放；D 可用冻结假事件做独立逻辑。丙不用同时管理 C、D。无需五个 AI 同改一个文件；本轮没有创建聊天、代理或工作树。

## 以后创建工作树（本轮未执行）

仅在 `git rev-parse --verify HEAD` 成功、RESULTS 中基线号核实、用户决定开始模块后使用。若基线尚未提交，B/C/D 只能在当前基线只读审查；不伪造共同提交号、不对 unborn HEAD 建工作树。

```powershell
# 在主仓库；把 <baseline-commit> 换成已验证的真实完整哈希。
$baseline = '<baseline-commit>'
git rev-parse --verify "$baseline^{commit}"
git worktree list
git branch --list 'codex/*'
# 确认目标目录不存在、分支不重名，一次只创建当前需要的工作树。
git worktree add -b codex/platform 'D:\智能驾驶赛\worktrees\platform' $baseline
git worktree add -b codex/data 'D:\智能驾驶赛\worktrees\data' $baseline
git worktree add -b codex/perception 'D:\智能驾驶赛\worktrees\perception' $baseline
git worktree add -b codex/mission 'D:\智能驾驶赛\worktrees\mission' $baseline
```

优先 A 留当前主目录维护集成，只建 B 当前所需的一个工作树；上面是备选步骤，不是一次性执行清单。已有分支先检查，不用 -B 重置。工作树不隔离摄像头、串口或 ROS master；本阶段所有模块离线。未跟踪/被忽略的历史资料不随工作树复制，阅读 reference 的版本化副本和本基线说明；更大资料只读引用主目录或 D 盘，不复制进代码树。

各模块开始时报告 `Get-Location`、`git branch --show-current`、`git rev-parse HEAD`、接口版本。提交时明确列出所属文件，不用 `git add .`；交付测试命令/实际结果/数据分组/新增依赖/未知项。A 检查提交范围和接口后串行合并与回归，不自动部署。
