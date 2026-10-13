# DEEPBOT 被动双路数据工具

本模块可在无 ROS 本机完成合成双路记录、事件、导出、质检；ROS 1 入口仅订阅已经存在的数据流。不会启动 master、相机或底盘，也不会发布速度。

- [HANDOFF.md](HANDOFF.md)：本轮实际结果、四步命令、A 的 20 秒静态采集卡与限制。
- [SCHEMA.md](SCHEMA.md)：`deepbot.data/0.1.0` 存储格式及与 A 冻结接口的适配边界。
- `python -m competition.data_tools --help`：start / stop / event / export / inspect。
- `python -B competition/tests/data_tools/run_checks.py`：仅合成测试，每次保留新输出目录。

从仓库根目录运行，Python 3.8+ 和 Pillow；ROS 入口另需现有 ROS 1 rospy/标准消息依赖。实际离线验证环境 Python 3.12.14、Pillow 12.3.0，无 rospy/rosbag。现场入口尚未运行验收。

`visual_only` 不要求运动反馈，禁止输出有动作标签的示范；`demonstration` 要求反馈就绪。high/low 仅为安装角色，物理身份/话题由配置指定。示例 JSON 中的 synthetic 话题是虚构测试话题；vehicle 示例来自 A 的历史观察，当前设备已关闭，使用前必须核对。

关闭完整不等于数据质量通过、身份实物验收或自主成功。所有原始数据保留；派生只新增、不覆盖。测试和样例产物在 `outputs/`，不纳入生产代码；小型实际报告保存在 `evidence/`。
