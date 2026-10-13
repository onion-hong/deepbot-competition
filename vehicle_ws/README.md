# DEEPBOT 车载源码工作区

这是从2026-10-13实际车载工作区整理的ROS 1 Noetic源码，不是Windows程序，也不是已通过编译/整车验收的发布镜像。厂商原件、首次快照及两次补充快照均保留。此次只读补取没有启动相机、ROS节点、串口或底盘。

默认 `src/` 是**6个代码包＋1个资源包**：riki_msgs、deepbot_driver、uvc_camera、imu_calib、deepbot、robot_localization，以及补齐真实URDF/STL后的deepbot_description。23包中的其余16包、核心包不在本阶段使用的旧入口/配置放在 `legacy_packages/`，根有 `CATKIN_IGNORE`，不参与默认catkin构建。不是把不同版本的同名包同时放进src。详细包列表、来源与依赖见[包清单](../competition/docs/vehicle_source/PACKAGES.json)。

构建文件、msg/srv、头文件、源码、必要launch/config、真实许可证、CMake模板、URDF和8.86MB原始STL已整理。默认串口bringup所引用的本地文件静态闭合；保留厂商CPP运行逻辑、0.5秒WallTime watchdog及析构零速。新启动入口默认 `enable_hardware=false`，相机/底盘均不开；启用后默认运动/舵机命令话题隔离到 `/vehicle_disabled/*`。这不是已验收的运动锁，不得用启动命令替代下一次现场授权。历史脚本可能打开设备、发速度、下载模型或清空训练目录，仅供审查。

## Ubuntu 20.04 / ROS Noetic 编译

使用已准备好的Ubuntu 20.04、ROS Noetic、Python3.8环境。当前Windows没有可用Linux ROS环境，以下是**待执行命令**，没有声称catkin成功。不要为本次验证在车上安装依赖或启动节点。

```bash
# 在克隆仓库根目录，离线源闭合检查（只用Python标准库）
python3 competition/docs/vehicle_source/audit_workspace.py
source /opt/ros/noetic/setup.bash
cd vehicle_ws
# 只查询已安装依赖；若缺失，保存输出，停止构建并按DEPENDENCIES.md准备环境。
rosdep check --from-paths src --ignore-src --rosdistro noetic
# 本次编译范围明确限制src，默认不编译/执行厂商测试（测试bag未附带）。
catkin_make -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCATKIN_ENABLE_TESTING=OFF -DPYTHON_EXECUTABLE=/usr/bin/python3
catkin_make install -DCATKIN_ENABLE_TESTING=OFF -DPYTHON_EXECUTABLE=/usr/bin/python3
source install/setup.bash
# 下面只读包路径、消息文本；不启动ROS master或设备。
rospack find deepbot_driver
rosmsg show deepbot_driver/Servo
rosmsg show riki_msgs/Velocities
```

依赖解析和编译失败意味着本环境不能重建，不是传感器故障；不得加空msg、删失败检查或借车上devel生成物绕过。`robot_localization`保留车载2.6.8源码，不能默默用另一个版本的二进制替代。catkin/编译器/完整依赖版本须由首次Linux构建记录；目前未冻结可复现容器镜像或apt快照。

## 范围与已知缺口

- [构建与运行依赖](../competition/docs/vehicle_source/DEPENDENCIES.md)：核心闭环依赖以及legacy外部组件分开列出；不自动联网安装。
- [来源、改动与交接](../competition/docs/vehicle_source/HANDOFF.md)：逐文件原始/整理后哈希、逐项diff、静态检查及权限清单。
- [第三方声明](NOTICE.md)：包内原有署名保留；TODO许可证仍未知，不能用仓库整体许可证覆盖。YOLO内嵌LICENSE与包元数据存在不同声明，待维护者核实。
- [外置资产与legacy缺口](../competition/docs/vehicle_source/EXTERNAL_ASSETS.md)：权重、训练图像、bag、地图、校准及固件不随源码发布；有哈希的列哈希，没有的明确未知。

相机本次映射高位video0/低位video2，USB by-path来自只读证据，重插后要复核。空format/相同frame_id的行为未改；无有效720P标定，不能把URDF模型当实测净空。当前仍缺比赛运动控制器、真实高级事件及闭环验收。

本目录只在总控审查后统一提交/推送；A整理期间未做Git写操作。根README由总控维护。
