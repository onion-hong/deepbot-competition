# DEEPBOT 智能驾驶赛项目

三人团队的比赛工程。目标是通过可靠采集、感知、任务决策与控制，逐步完成正式比赛任务。

## 当前进度

已实现双相机记录/导出/质检、道路像素感知与离线回放、两圈任务证据状态机。2026-10-13 的离线阶段通过 90 项测试及 6 帧记录→导出→感知贯通检查。

车载 ROS 源码现已整理入库：7 个默认包（6 个代码包＋1 个资源包），16 个隔离历史包。干净 Git 副本复验与交付范围见 [仓库交付记录](competition/docs/REPOSITORY_DELIVERY.md)。

**当前不是可以直接启动实车完成比赛的程序。** 真实双相机记录尚待验收；目标识别、真实任务事件、绕桶/环岛/倒库的运动执行仍需开发。离线任务模块目前输出停车请求。

## 队友从这里开始

**下一次现场从[详细执行步骤与分工](competition/docs/team/NEXT_SESSION_PLAN.md)开始：手柄采集有用路段，停车后当场回放；不单设静止20秒关卡。** 决策复核与多对话约定见 [AGENTS.md](AGENTS.md)。

通用背景见 [三人协作与推进顺序](competition/docs/team/TEAM_GUIDE.md) 和 [数据采集规范](competition/docs/team/DATA_COLLECTION.md)。下面的命令用于电脑上的离线验证；车载 ROS 源码与构建范围见 [vehicle_ws](vehicle_ws/README.md)。

```bash
git clone https://github.com/onion-hong/deepbot-competition.git
cd deepbot-competition
python -m venv .venv
```

激活虚拟环境：Windows PowerShell 执行 `.\.venv\Scripts\Activate.ps1`；Linux 执行 `source .venv/bin/activate`。以下使用激活后的解释器，在仓库根目录运行：

```bash
python -m pip install -r competition/data_tools/requirements.txt -r competition/perception/requirements.txt
python -B -m unittest discover -s competition/tests/offline -p "test_*.py" -v
python -B -m unittest discover -s competition/tests/data_tools -p "test_*.py" -v
python -B -m unittest discover -s competition/tests/perception -p "test_*.py" -v
python -B -m unittest discover -s competition/tests/mission -p "test_*.py" -v
python -B competition/tests/offline/verify_data_perception.py --output competition/tests/offline/outputs/my_first_run
```

已验证的本地环境为 Python 3.12、NumPy、Pillow；车载 Python 3.8/ROS Noetic 的真实接入仍待验证。最后一条命令输出目录必须是新目录，重复执行请换名称。生成图像与日志保留在本地，不提交 Git。

## 目录与交接

| 目录 | 内容 |
|---|---|
| `vehicle_ws/src` | 默认构建的底盘、消息、相机等核心 ROS 包 |
| `vehicle_ws/legacy_packages` | 隔离保存的其余厂商 ROS 包；不参与默认构建 |
| `competition/data_tools` | B：采集、导出、质量检查；见 [交接说明](competition/data_tools/HANDOFF.md) |
| `competition/perception` | C：道路感知、离线回放；见 [交接说明](competition/perception/HANDOFF.md) |
| `competition/mission` | D：任务状态机；见 [交接说明](competition/mission/HANDOFF.md) |
| `competition/interfaces` | 公共数据格式与验证器 |
| `competition/platform`、`control`、`launch` | A：车载适配及控制的后续集成位置 |
| `competition/reference` | 厂商与历史参考源码，保留来源署名，不能批量执行 |
| `competition/docs/team` | 队友上手、分工、数据采集与共享流程 |
| `competition/docs/vehicle_source` | 车载源码来源、补取清单与修改记录 |
| `competition/docs/repository_audit` | 源码依赖、资源与许可证的静态审查 |

详细结果与能力边界见 [阶段集成收据](competition/docs/OFFLINE_STAGE_RECEIPT.md)。各交接文件中的本机路径和 `uncommitted` 是当时的记录；当前版本以 Git 为准。文档提到的部分现场报告和测试产物只在原电脑保存，需要队内另行共享。

本仓库提供比赛开发代码和整理后的车载 ROS 源码。原始录像、训练数据、模型权重、系统镜像及 MCU 固件资料另行管理，不随克隆下载。后续优先复用现有驱动，在 `competition` 中开发比赛功能；修改厂商包时保留来源并记录差异。源码已入库、离线测试通过、ROS 编译通过、实车完成比赛是不同的验收阶段，不能相互替代。

## 协作约定

- 各自修改分配的模块，公共接口变更先协调；开发前拉取更新，用自己的分支提交。
- 公有仓库可直接查看和克隆；直接推送需要仓库协作者权限，也可以使用 Fork 和 Pull Request。
- 不提交录像、采集原图、模型权重、密码、连接密钥或现场配置。提交前查看 `git status` 和差异，按明确文件暂存。
- 只运行上面指定的测试目录。历史参考程序可能启动 ROS、训练或清理数据，不能在整个仓库盲跑所有测试。

公开访问不等于所有文件采用统一开源许可证；厂商参考代码保留原作者权利，本仓库未替其附加许可证。
