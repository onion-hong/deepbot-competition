# 本地准备交付结果（2026-10-13）

**后续状态更新（现场只读阶段）：** 原51项与 `tmp/baseline_receipt.json` 全部一致后，通过工具受控提权完成精确暂存与本地提交，真实基线为 **`cd3d33415bbe4b753c1340a333ac6bc51e0c3927`**。索引逐文件核对通过（仅Git规定的文本换行归一化），未混入B/C/D新增文件、未推送/切分支。下面“无提交/Permission denied”保留为上一阶段的真实历史。最新现场交接见 `VEHICLE_HANDOFF.md`，独占开发规则见 `OWNERSHIP.md`。

工程标识：`deepbot-local-20261013-v1`。接口冻结：`deepbot.offline/0.1.0`。

Git 起始状态已核实为 master 无提交、索引空；`git remote -v` 无输出。按51项清单实际执行 `git add --pathspec-from-file=competition/docs/BASELINE_FILES.txt`，退出1，报 `.git/index.lock: Permission denied`。因此**尚无基线提交号，未暂存、未执行commit、未推送**。这是文件系统拒绝写.git，不是提交成功，也不是分支冲突。未解除权限、未改用别的仓库绕过。最终复核：`git status`仍报告No commits yet on master，`git ls-files --stage`为空，`git rev-parse --verify HEAD`失败。

已新增：根 .gitignore/.gitattributes、competition 最小结构、24份原样来源副本、离线schema/验证器/10条样例、无硬件配置、13项纯合成回归、文件所有权/今日操作卡/车载只读采集卡/来源审查和精确清单。历史目录、原源码和证据未覆盖；D盘资料只读。

实际验证：

- `python -B -m unittest discover -s competition/tests/offline -p 'test_*.py' -v`：13项通过。
- `python -B -m competition.interfaces.validate competition/interfaces/examples.jsonl`：10条合成记录通过。
- 24份参考副本与本地原件逐字节、SHA-256一致。
- 最终51项纳入文件已扫描，无超过1MiB文件、意外扩展名或模型；6处启发式命中均为密钥忽略规则/隔离测试回环地址。精确排除和范围见GIT_SCOPE。
- 27个历史Python文件只做AST静态审查；新增及参考Python只解析语法，不执行历史入口。
- 本轮测试入口已在执行前检查：只导入标准库与新离线验证器，读取合成JSON，无ROS、网络、摄像头、串口、训练、模型加载或子进程。

执行环境：Codex bundled Python，实际版本见 OFFLINE_TESTS.txt。本机该解释器无ROS/OpenCV/jsonschema；新增检查只用标准库，不安装依赖。真实执行的是 `-X utf8 -B`，避免中文控制台乱码及写缓存。

最终逐文件SHA-256与整个纳入集合的内容指纹保存在本机 `tmp/baseline_receipt.json`，方便核对提交前内容，**它不是Git提交号**。该收据不纳入清单，避免自引用哈希。

范围限制：没有运行历史ROS/虚拟串口测试；没有完整catkin构建、双相机编码/解码验证、感知准确率测试、任务状态机实现或整车测试。样例中的图像路径是占位，不是实拍数据。离线时间检查不能作为运动授权。

工作树尚未建立，后续步骤见 OWNERSHIP.md；只从真实已提交基线创建，优先只开B一个离线开发工作树，C/D按文件分工、分时推进。最终车辆发布入口与集成归A。

## 在可写 .git 的本机终端完成基线（本轮未执行成功）

在同一个主仓库根目录依次运行；遇错误停止，不添加未知文件：

```powershell
git status --short --branch
git diff --cached --name-only
# 预期仍无提交且索引空；若有别人的暂存修改，先停下交A核对。
git add --pathspec-from-file=competition/docs/BASELINE_FILES.txt
if ($LASTEXITCODE -ne 0) { throw 'Git add failed; do not commit' }
$baselineExpected = Get-Content competition/docs/BASELINE_FILES.txt
$baselineStaged = git -c core.quotePath=false diff --cached --name-only
$baselineDifference = Compare-Object ($baselineExpected | Sort-Object) ($baselineStaged | Sort-Object)
if ($baselineDifference) { $baselineDifference; throw 'Staged paths differ from reviewed allowlist' }
git diff --cached --stat
git diff --cached --check
```

参考副本保持原始字节，diff --check 若报告旧文件空白问题，先确认仅在reference，不能为消除提示修改历史来源。新增文件若有问题交A修复并重审清单。核对完后：

```powershell
git commit -m "Establish DEEPBOT offline engineering baseline and interface v0.1.0"
if ($LASTEXITCODE -ne 0) { throw 'Commit failed; no baseline hash may be claimed' }
git rev-parse --verify HEAD
git status --short --branch
```

把真实完整HEAD发给B/C/D，并记录到下一次交接；不把本次工程标识/文件哈希当Git提交。没有外推到实车的许可。若本机同样拒绝写.git，停留在已准备基线，等待目录权限问题解决。
