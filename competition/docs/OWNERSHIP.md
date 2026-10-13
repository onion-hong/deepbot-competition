# 文件所有权与依赖

| 负责人 | 可修改路径（均相对仓库根） | 依赖与交付 |
|---|---|---|
| A 总控/甲 | competition/platform、competition/control、competition/config、competition/launch、competition/interfaces、competition/docs、competition/tests/offline；根 .gitignore/.gitattributes | 唯一Git/设备负责人；维护接口、基线、最终仲裁/集成 |
| B 数据/乙 | competition/data_tools、competition/tests/data_tools | 读冻结接口和参考记录/导出；双路离线记录/配对、质量报告、会话回读 |
| C 感知/丙 | competition/perception、competition/tests/perception | 读B帧格式与冻结接口；输出road/detections与失败例 |
| D 任务 | competition/mission、competition/tests/mission | 假事件先开发，后接C；交圈数/等杆/倒库逻辑与motion_request |

reference/**、历史原件、原始数据全部只读。模块说明、失败报告、依赖需求写在各自目录，不共同修改 docs/RESULTS.md。B/C/D 不改公共接口、底盘或最终 launch；提出变更理由和输入输出样例，由 A 冻结新版本。README 占位文件不是已实现功能。

2026-10-13总控已协调在同一主项目内按上述目录独占开发；没有工作树不再阻止B/C/D离线实现。B不SSH，C/D不接设备，各模块不写Git、不切分支、不清理/重置、不移动他人文件。禁止旧路径tests/data（被忽略）；统一competition/tests/data_tools。A本对话没有创建聊天、代理或工作树。各模块之间交付由总控查收，A负责集成。

## 以后创建工作树（本轮未执行）

原51项已审基线提交：`cd3d33415bbe4b753c1340a333ac6bc51e0c3927`。当前先保持目录独占，不在其他模块开发期间切分支或迁移。以后用户要求隔离工作树时，先由A核对并保存各模块未提交成果，再从明确提交创建；不伪造共同提交号，不把初始基线当成包含新模块成果。

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

各模块开始时报告 `Get-Location`、`git branch --show-current`、`git rev-parse HEAD`、接口版本。模块交付明确列出所属文件与源码哈希、测试命令/实际结果/数据分组/依赖/未知项。只有A按精确清单暂存提交，审查前不把B/C/D成果混入基线，不用git add .；不自动部署。
