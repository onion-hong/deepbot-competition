# 来源与第三方声明

本目录不是统一许可证的新项目。源码来自2026-10-13只读取得的实际车载catkin_ws/src及两次限定补取；保留原文件中的版权、作者、维护者与许可证声明。逐文件SHA、来源路径、改动diff见 `../competition/docs/vehicle_source/`。维护者邮箱是原有署名，不因隐私扫描删除；TODO占位不是本团队取得授权的证明。

- uvc_camera与camera_umd的package.xml声明GPLv2；uvc_cam.h保留Morgan Quigley的GPL v2或以后版本声明。uvc_camera/COPYING附完整GPLv2原文，逐字节取自本机Git for Windows分发的COPYING.GPLv2，来源哈希见LICENSE_TEXT_SOURCE.json，不伪装成从车上取得的原文件。
- robot_localization和imu_calib的实际LICENSE已从各原包补取；代码头部许可证保持不变。deepbot_line_follower的LICENSE.md、Darknet的LICENSE、内嵌YOLOv5的LICENSE均随对应legacy源码保留。
- deepbot_driver等多个包仍是`license=TODO`；deepbot_description作者/维护者仍有TODO占位。资源包的空维护者name仅补成“Upstream maintainer name not supplied”以满足元数据非空，不虚构作者或授予许可证。
- riki_msgs、deepbot、deepbot_description、opencv_apps等包的BSD字段是包元数据声明；不等于已独立核实全部厂商改动/模型/资源的再分发权。未找到的LICENSE没有臆造。
- rikibot_yolov5包声明APLv2，而内嵌yolov5/LICENSE为另一实际许可证正文；它们须分别审查，不能用外层字段覆盖内嵌代码。Darknet/ROS包装层亦分别保留声明。

详细23包声明在PACKAGES.json。公有共享是用户的发布意图，但整理工作没有补齐未知授权；总控发布时应将这份未知清单同时交给维护者，不宣称全仓BSD/MIT或已经完成法律审查。没有改变仓库可见性、没有另建仓库，也没有替原作者签署授权。
