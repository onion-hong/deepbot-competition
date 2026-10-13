# 下一阶段车载缺失清单与只读命令卡

本文件只是后续计划。本轮未 SSH、未查询车上实时状态。需要用户另行授权只读接入；当前不提供旧 IP/私钥作为可直接运行的连接命令。以下 bash 片段供已获授权、已人工进入小车终端后逐条执行。不要启动 ROS master、相机、底盘、训练或烧录来“补齐结果”。无输出/找不到就是缺项，不自动修复。

## 必须补齐的内容

| 缺项 | 目的 | 目前依据与限制 |
|---|---|---|
| OS/ROS/架构/Python/OpenCV/OpenVINO 实际版本 | 决定依赖和构建 | 历史 Ubuntu20.04/Noetic，不是当前在线核验 |
| 完整 catkin src 的 package.xml、CMakeLists、依赖锁、launch、yaml、cfg、msg/srv | 可重构建和映射消息 | 本地只有局部源码；不创建假的工程描述 |
| DriverMode.msg、Servo.msg、riki_msgs/Velocities、实际 vision_msgs 定义/MD5 | 字段/版本与线上消息一致 | 源码 import/include 不能代替定义；vision_msgs 各版本字段差异待核实 |
| 当前部署的驱动源/二进制及哈希、全部启动与 remap | 确认 watchdog 是否实际启用及速度发布者 | 历史 patch 的 0.5s 超时保留；未确认线上版本 |
| raw_odom→odom 节点、坐标、时间与单位 | 区分实测/融合/指令，解释响应差异 | 原始驱动固定0.02s积分、主机打戳；/sonar单位未知 |
| 两相机物理映射、分辨率模式、安装方向、标定及时间来源 | 真实双路身份、回放坐标、倒库视野 | 历史同序列号冲突；高/低不等于前/后，旧640×480标定不能用于720P |
| 串口/udev、固件与镜像版本证据 | 匹配硬件文档和校准入口 | 2025文件夹含2023旧手册；补充“需更新”不是刷机授权 |
| 当前权重、类别表、预处理/输出维度、模型哈希 | 判断可复用性与训练必要性 | 旧代码仅 start/crossing；未加载模型 |
| 当前进程、设备占用、ROS节点/发布者 | 防止多来源控制冲突 | 历史已释放记录不能当今天状态 |
| 正式摆位、车外廓/车轮/库口尺寸、后方盲区 | 决定入库和净空 | 由三人现场量测，不能从截图编造 |

## 分步只读采集

1. 系统和占用。仅显示版本/进程名/设备链接，不列进程完整参数或全部环境变量（可能含凭据）。

```bash
date -Ins
cat /etc/os-release
uname -m
ls -d /opt/ros/*
printenv ROS_DISTRO
python3 --version
dpkg-query -W 'ros-*-ros-core' 'ros-*-vision-msgs' 'ros-*-cv-bridge' 'python3-opencv'
python3 -m pip show openvino numpy torch
ps -eo pid,comm
ss -lnt
ls -l /dev/v4l/by-id /dev/v4l/by-path /dev/serial/by-id /dev/deepbotbase
fuser /dev/video* /dev/ttyUSB* /dev/deepbotbase
```

预期：系统/包版本、监听端口和占用 PID、相机/串口稳定链接。fuser 无占用通常退出 1；权限不足不是“无人占用”。pip show 只读元数据、不 import torch/模型；包不存在记缺失。`ls /opt/ros` 并不能证明当前进程所用版本。

2. 已有工作区文件和依赖。先确认路径；不运行 setup 脚本（脚本可能有环境钩子），不 build、不安装。

```bash
ls -ld /home/deepbot/catkin_ws/src /home/deepbot/catkin_ws/devel
find /home/deepbot/catkin_ws/src -type f \( -name package.xml -o -name CMakeLists.txt -o -name '*.msg' -o -name '*.srv' -o -name '*.launch' -o -name '*.yaml' -o -name '*.cfg' \) -print
find /home/deepbot/catkin_ws/src -type f \( -name '*.pth' -o -name '*.pt' -o -name '*.onnx' -o -name '*.xml' -o -name '*.bin' \) -printf '%s %p\n'
ls -l /etc/udev/rules.d
```

预期：实际包/定义/配置路径及模型大小，不读取训练数据或镜像。选定文件后用 `sed -n '1,220p' <已核实文件>` 读文本、`sha256sum <已核实文件>` 计算哈希。模型哈希顺序执行避免长时间 I/O，不能 import/pickle-load 权重。udev 只看与车相关规则。复制源码前审查文件名/内容、排除密钥、个人目录和数据，复制到新的本地快照目录并核对哈希；不对整个 home 打包。

3. ROS 查询只针对已经运行的 graph。在已配置 ROS 环境终端里先 `command -v rosnode rostopic rosmsg`；命令不存在则记录，不自动 source/启动。若环境正确且 master 已运行：

```bash
timeout 5s rosnode list
timeout 5s rostopic list -v
timeout 5s rostopic info /cmd_vel
timeout 5s rostopic info /raw_odom
timeout 5s rostopic info /odom
timeout 5s rostopic info /sonar
rosmsg show -r deepbot_auto_driver/DriverMode
rosmsg md5 deepbot_auto_driver/DriverMode
rosmsg show -r deepbot_driver/Servo
rosmsg show -r riki_msgs/Velocities
rosmsg show -r vision_msgs/Detection2DArray
rosmsg md5 vision_msgs/Detection2DArray
```

预期：发布者/订阅者、真实类型和递归字段、MD5。超时退出 124 表示本次无结果，不能推出节点不存在；包不存在保留 stderr。不要用 `rosparam dump /` 收集全部参数或凭据，仅在核对节点后对特定非敏感参数逐项 `rosparam get /<节点>/<参数>`。rospack find/profile 可能写缓存，本卡使用文件清单定位。

4. 帧/反馈时间戳采样要先确认发布者已在发布；某些驱动在有人订阅后才启采，未知时不订阅图像。已确认不会启动设备的数据流才可查询：

```bash
timeout 5s rostopic echo -n 1 /raw_odom/header
timeout 5s rostopic echo -n 1 /raw_odom/twist
# 用上一步确认的类型/话题替换占位，且只针对已有连续发布流。
timeout 5s rostopic hz /<已确认持续发布的话题>
```

预期：来源时间、frame_id、实测反馈、观察频率；timeout 到期为结束观察，不计控制成功。双路真实图像采集属于后续明确窗口，不通过本卡启动它。禁止 rostopic pub、服务调用、roslaunch/rosrun、v4l2 开流、serial open、kill、刷机和 chmod 设备。

## 回传格式

每条保存：命令、开始/结束时间、退出码、原始输出、本地文件位置、已核实/未知、来源哈希。去掉公网凭据/操作者实名再纳入版本。失败输出也保留。只有取得实际定义后由 A 新增明确的 ROS 1 适配映射，继续保留离线 0.1.0 的兼容约定。
