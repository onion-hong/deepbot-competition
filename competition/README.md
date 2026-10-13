# DEEPBOT 本地工程基线

> 以下保留 2026-10-13 最初基线阶段的说明，其中“尚未实现/确认”描述当时状态。当前已交付 B/C/D 离线模块及现场接口快照，请先读仓库根 [README](../README.md) 和 [阶段集成收据](docs/OFFLINE_STAGE_RECEIPT.md)。

接口 `deepbot.offline/0.1.0`，工程标识 `deepbot-local-20261013-v1`。这是可独立运行接口回归的本地准备基线；不是可部署的完整 catkin 工作区，也不是比赛算法或整车验收结果。

历史源码显示 ROS 1（roscpp/rospy）；历史设备记录为 Ubuntu 20.04 / ROS Noetic。当前车载发行版、包版本、消息 MD5 和部署文件尚未重新确认。没有建立 ROS 2 包，没有编造 `.msg` 或已部署话题。

先读 `docs/TODAY.md`，然后读 `interfaces/CONTRACT.md`、`docs/OWNERSHIP.md`。精确版本纳入清单在 `docs/BASELINE_FILES.txt`，来源及原件哈希在 `docs/PROVENANCE.json`，结果和限制在 `docs/RESULTS.md`。

## 唯一本轮测试入口

从仓库根目录，用 Python 3.8+ 标准库运行：

```powershell
python -B -m unittest discover -s competition/tests/offline -p 'test_*.py' -v
python -B -m competition.interfaces.validate competition/interfaces/examples.jsonl
```

若 `python` 不是已核实的解释器，先运行 `python -c "import sys; print(sys.executable)"`。本轮实际解释器与命令见 RESULTS。无需安装 ROS、OpenCV、模型或第三方包。只对 `tests/offline` 做测试发现，不能在仓库根目录盲跑 pytest/unittest。

## 复用路径

- `reference/original/`：原厂巡线、路线、检测、学习驾驶与配置的原样来源副本。
- `reference/patched/`：已有底盘 watchdog、巡线停车保护、单相机被动记录和导出、相应历史测试的原样副本。
- `platform/`、`control/`、`launch/`：A 的接入和集成位置，目前只有边界说明，没有硬件启动入口。
- `data_tools/`、`perception/`、`mission/`：B/C/D 的开发位置，目前没有冒充已实现的双相机或两圈算法。

reference 下源码只供阅读与选择性复用，不能直接运行或批量 import。尤其 train.py 顶层训练，params.cfg 顶层生成配置，data_collect.py 构造时删除旧目录，若干历史测试顶层执行进程/ROS操作。参考文件没有接入任何新启动器。

正式赛道已到，环岛逆时针来自用户确认；旧黄线练习数据仅可诊断。历史未完成正式两圈，单相机合成记录测试不证明真实双相机采集成功。10 月 28 日冻结功能，10 月 31 日为团队验收目标。
