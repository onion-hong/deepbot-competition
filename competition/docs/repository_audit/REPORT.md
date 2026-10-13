# 仓库独立可交付性最终审查 — 2026-10-13

**结论：截至本次最终文件枚举，未发现阻断“明确标注范围的源码归档共享”的未解决文件/清单问题。** 这不是 Linux/ROS 构建通过、所有历史功能可运行或实车部署许可。总控已设置执行位；本审查最后只读确认87/87项为100755，994/994暂存blob哈希匹配。干净副本测试由总控独立执行，本审查不代为宣称通过。

审查时 HEAD：186d367bbd2ecc518149d2c3a24432c3aeed3f04。仅写 competition/docs/repository_audit；没有修改模块、Git、仓库可见性，没有 SSH、ROS、相机、串口、训练或运动操作，也没有重复90项离线测试。已读 A 最终 HANDOFF、README、NOTICE、依赖与外置资产说明。

## 最终实际枚举

| 范围 | 结果 |
|---|---|
| 核心 src | 7 包、164 文件：6代码包＋deepbot_description资源包 |
| 历史 legacy_packages | 16 个 package.xml、825 文件；另含核心包的历史入口片段 |
| 全 vehicle_ws | 994 文件，23 个唯一包名，无重名 package.xml；不是旧“6/17”口径 |
| 自定义接口 | 核心17 msg＋13 srv，历史34 msg＋1 srv，合计51 msg＋14 srv |
| WORKSPACE_FILES | 994/994 文件存在且 SHA-256 匹配；无未列入文件 |
| 来源映射 | 988 条、988 个唯一目标，原始快照文件及源哈希可复核，目标记录哈希无不一致 |
| 核心字面 CMake / launch | 已解析的构建输入与本地 launch 引用缺失均为0；CMake组件声明与package.xml差异为0 |
| 真实几何 | deepbot_description URDF 的两处 package://.../base_link.STL 均存在；原STL不是自造替代 |
| 入口保护 | driver、bringup、dual_camera 三入口 enable_hardware 默认false，无未受该group约束的node/include |
| 执行位候选 | A清单87个文件均存在，均有LF shebang；已只读确认87/87暂存mode=100755 |
| 文档引用 | vehicle_ws README的5条本地链接全部存在 |

静态程序不完整解释 CMake 变量、条件和宏，也不验证系统库、链接器、节点加载或实际时序。OpenCV Apps 的nodelet生成宏已识别，未把宏产生的camshift等误报为缺失可执行文件。

## 初审具体问题的处置

1. **缺模板已解决**：原快照 opencv_apps/CMakeLists.txt:115 所用 src/node/standalone_nodelet_exec.cpp.in 已真实补入 legacy，来源哈希可查。
2. **核心依赖声明已解决**：deepbot_driver 的 riki_msgs/serial 等已补，消息生成/安装声明修整；核心7包静态声明闭合。deepbot_auto_driver、deepbot_line_follower、deepbot_yolo_detection、opencv_apps、yolov5_ros_msgs 的原声明差异仍保留在历史范围，不把其恢复运行称为已支持。
3. **核心资源闭合已解决**：真实 URDF/STL 及默认入口所需 YAML 存在。历史启动仍有 25 条本地解析引用不可直接满足，主要为外置权重、Gazebo旧路径，以及旧相机/导航入口仍按原包路径查找已隔离资源。完整逐条证据在 audit.json.combined_workspace.launch_references；它们属于已声明不支持的legacy部署限制，非本次核心共享阻断。
4. **包名处理正确**：原 deepbot_msgs→riki_msgs、deepbot_auto_drvier→deepbot_auto_driver；副本按真实包名组织，跨核心/历史没有重复package.xml。
5. **最后清单不同步已解决**：初次末检发现989项清单漏掉README/NOTICE/.gitattributes和2个udev文件；A刷新后994项完整，已独立重新核对。旧记录在本聊天，不用旧计数作最终结论。

## 行尾与可复核哈希

根 `.gitattributes` 的 `vehicle_ws/** -text` 合适；目录内 `* -text` 同样保证不做Git行尾转换。最终对994个清单路径调用只读 git check-attr，全部 text=unset。对核心CMake、uvc C++和legacy Python三类代表文件分别比较 git hash-object --no-filters 与带 --path 的过滤结果，三者均字节一致；没有使用-w、没有写index或object。

A的SHA-256记录针对文件原始字节，因此在此范围关闭文本转换能保留可复核性；即便继承eol=lf，text=unset仍关闭转换。不必取消其他目录既定LF策略。87个需执行位脚本的首行均无CRLF，避免为了保留字节而悄悄引入Linux shebang问题。今后修文件需更新目标哈希/差异，不能只重写原始来源哈希。总控仍需按其计划在干净克隆中核验哈希和执行位。

## 许可证与公有分享边界

23包的原始字段仍是BSD 8、GPLv2 2、MIT 1、APLv2 1、TODO 11。保留原文，不把APLv2自行改写为另一已确认授权，不给TODO包补MIT。最终已补入robot_localization/imu_calib实际LICENSE、deepbot_line_follower LICENSE.md、内嵌YOLOv5 LICENSE、Darknet LICENSE；uvc_camera完整GPLv2文本单独注明来自本机Git发行版，没有冒充车辆原件。

可直接观察到内嵌yolov5/LICENSE为GNU GPL v3，而外层rikibot_yolov5/package.xml声明APLv2；Darknet LICENSE标题为YOLO LICENSE。package字段不能覆盖这些文件。详情及初始D盘证据在 NOTICE_INVENTORY.md、vehicle_ws/NOTICE.md 和 audit.json。未知授权仍是明确已知项；用户选择公有分享保持不变，本审查不改变可见性，也不宣称完成法律许可核实。

D盘初审范围不重复扫描：排除环境/cache后76文件，12 ZIP索引、1 RAR未打开；两份MCU源码包分别666/983成员。无裸ROS package.xml，未还原系统镜像；固件许可证不推定为ROS包许可证。

## 三类交付能力

- **可构建性**：仅静态闭合。未执行catkin_make/install，Windows没有可用Linux ROS；总控已报告WSL HCS_E_SERVICE_NOT_AVAILABLE，本审查未重复尝试。外部依赖版本和首次真实编译/链接结果待单独记录。
- **可离线测试**：competition已有离线入口，本轮不重复运行，不用旧测试通过证明新增ROS代码可构建。A静态审计工具与本独立检查均不执行车载源码。
- **可实车部署**：未验证。模型/数据/地图/标定仍外置，legacy不能整体启用。守护入口不等于已验收运动锁，udev原MODE=0777仅归档未安装；没有依据这些文件启动设备。整车运动、相机时效、停稳、比赛控制器/高级事件/闭环仍待后续阶段。

## 可复查文件与命令

- audit.json：完整初始盘点、最终核心/历史/组合枚举、逐项引用、最终结论。
- delivery_checks.json：独立哈希、来源、资源、开关、执行脚本及Git过滤检查。
- index_checks.json：994项暂存blob哈希与87项执行位的最终只读核对。
- initial_inventory.json：第一轮source/D盘证据，保留不改写成最终状态。
- NOTICE_INVENTORY.md：逐包原始声明与新增授权文本说明。

在仓库根运行（只重做静态检查；输出仅本审查目录）：

```powershell
python -B competition/docs/repository_audit/audit_repository.py --phase final
python -B competition/docs/repository_audit/verify_delivery.py
```

这两条会刷新机器枚举，不自动重写本文的人工审查结论；源码再次变化后应比较结果，不能直接沿用本次结论。最终暂存/执行位/干净克隆验证与推送由总控完成。

最终冻结补充：A清单为994文件/988映射/14项已记录修改；总控暂存后，本审查读取git ls-files及git cat-file（无写入），994项index blob SHA-256均与清单一致、87项执行位均100755、无未合并index项。干净Git导出仍由总控继续。
