# A交接：车载源码归档（2026-10-13）

实际写入 `vehicle_ws/`、本目录和根.gitignore；没有修改根README、B/C/D代码或公共契约，没有Git写操作/提交/推送。最终提交由总控统一执行。默认从现有公有仓库发布，不另建仓库或改变可见性。

最终盘点：vehicle_ws共**994文件、17,535,033字节**（含README/NOTICE/字节属性），988个目标有源快照映射，14个已有文件有整理diff；其他为明确新增文件/附加许可证。FILES_TO_STAGE共1014项（含.gitignore及本目录说明/清单），无条目被Git忽略；87项Linux执行位由总控统一设置。VALIDATION.static_pass=true，catkin与硬件验证均未运行。

## 交付结构与完整性

- 原快照23包全部有源码归档；默认构建**6个代码包＋1个资源包**：riki_msgs、deepbot_driver、uvc_camera、imu_calib、deepbot、robot_localization、deepbot_description。最后一个因URDF/STL补齐从隔离区提升，故不再沿用早期“6/17”的口径。
- `legacy_packages/`内16个完整包目录及核心的历史入口/资料，通过根CATKIN_IGNORE隔离；保留源码、msg/srv、配置、launch、CMake模板、CUDA源码、类别配置、许可证和必要几何资源。保留不等于所有旧功能可以运行：模型/数据、缺失外部包与旧路径缺口分别列出。
- `src/`仅一个版本的每个包，均来自此次实际车载源码。ROS1 Noetic是已核实的平台；生成Python消息包装器不参加归档，原msg/srv用于重建。没有造空消息或新造车辆几何。
- 首次只读快照基础上，经总控追加授权完成两次限定补取：138文件/1,727,950字节及52文件/10,050,318字节；第二次包括8,861,784字节STL。重叠源码未变化。两个新独立本地快照为 `vehicle_snapshot_20261013_source_supplement/`、`vehicle_snapshot_20261013_source_supplement2/`，不覆盖旧证据，不随公有Git发布。
- 第一次8MiB限制和扩展名遗漏已被第二次针对性补齐；不再把STL/CUDA/类别文件列为缺失。权重、原图、bag/地图和编译输出仍明确外置。复制出的模型XML已从新归档副本排除，原始补充快照保留，未动小车或原模型。

## 来源与改动

`SOURCE_INVENTORY.json`逐文件记录相对目标路径、源快照/源SHA、包名、纳入排除理由、目标SHA、是否修改。`PACKAGES.json`记录23包原依赖/许可证以及默认包的整理后依赖；`WORKSPACE_FILES.json`是全部工作区文件哈希；`CHANGES.patch`保留每个已有源文件的文本diff。

修整集中于构建/安装和启动入口：driver补消息/serial/tf2/nav/riki依赖、生成顺序及install，隔离引用不存在Python包的setup.py；deepbot修正不存在的库名/system_lib和运行依赖，补install；imu_calib显式PkgConfig/Eigen3；uvc_camera补pluginlib/Boost声明及许可证安装；robot_localization补并行消息生成依赖；description补资源安装、空维护者标识并隔离错误xtrobot路径入口。**原CPP/H实现及运行停车保护不变**。driver、相机和bringup默认不启设备；运动/舵机默认话题隔离。原完整launch仍在legacy。

真实LICENSE已补取，GPLv2全文另从本机Git发行版逐字节补附，来源清楚，不虚构车辆原文件。TODO许可证、内嵌YOLO声明差异和资源再分发未核实项见vehicle_ws/NOTICE.md；不要将整个归档改标BSD/MIT。

## 实际检查与边界

运行 `python -B competition/docs/vehicle_source/audit_workspace.py`：检查来源哈希、默认包唯一性、CMake静态源/msg/srv文件、XML/插件XML片段、Python语法、活动launch/URDF资源引用、4个默认关闭入口、凭据模式。实际结果写VALIDATION.json。插件XML片段语法检查不等于插件加载；声明/资源闭合也不等于编译。

Windows没有已确认可用Linux ROS。WSL情况已报告，不继续尝试/安装/改系统。**未执行catkin_make、ROS节点、相机、串口、模型加载或运动**。Ubuntu20.04/Noetic待执行编译及install命令见vehicle_ws/README.md；外部依赖见DEPENDENCIES.md。先在构建机验证，再另批现场阶段；当前不部署。

`audit_workspace.py`在原快照存在时校验原始与整理副本并重建diff；纯克隆没有私有快照时对已发布的目标哈希核验，保留既有diff。它只写本目录报告，不导入车载源码；不是ROS编译替代品。prepare/merge/amend脚本保留A整理过程，**不是用户安装入口**；最终资源提升/补取记录以清单和diff为准，勿在已有工作区重复整理。

## 总控提交操作

1. 先读NOTICE、VALIDATION和C审查。根.gitignore已仅为历史YOLO的代码/配置增加精确data/models例外，仍不放行原图/权重；目录所有预期源码应能被git识别。
2. `FILES_TO_STAGE.txt`列本次新增/修改文件；根.gitignore需合并总控并发变更。工作区使用字节保留属性，避免换行归一化改变原始来源哈希。A没有暂存。
3. `EXECUTABLE_FILES.txt`列87个具有shebang的Linux脚本/动态配置，供总控在精确暂存后逐项`git update-index --chmod=+x -- <path>`；其中多数是legacy，执行位不构成运行授权。核心C++可执行文件由catkin生成，无需给cpp加执行位。
4. 同时带上README/NOTICE与来源清单，不提交三个原始快照、模型、生成输出。公共0.1.0契约未改。若C发现具体缺口，修正新副本并重跑静态审计，不能把“静态PASS”写成“Linux编译成功”。

后续实际控制启动仍未实测；原udev规则放platform/udev仅用于映射核对，含原MODE=0777配置，不自动安装。核心带来的只是可重建源码候选，比赛运动控制器与真实高级事件仍是独立未完成的软件工作。
