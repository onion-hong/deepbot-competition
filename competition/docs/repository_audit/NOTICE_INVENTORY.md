# 原始许可证声明盘点（不是新授权）

仅报告本地导出快照实际声明；尚未据此确认整个仓库具有统一许可证。用户选择公有分享保持不变。本文件不替换原作者声明，也不为 TODO 包补造 LICENSE。

| package.xml 包名 | 目录 | 原始 license 字段 |
|---|---|---|
| camera_umd | camera_umd/camera_umd | GPLv2 |
| jpeg_streamer | camera_umd/jpeg_streamer | BSD |
| uvc_camera | camera_umd/uvc_camera | GPLv2 |
| deepbot | deepbot_project/deepbot | BSD |
| deepbot_ar_track | deepbot_project/deepbot_ar_track | BSD |
| deepbot_auto_driver | deepbot_project/deepbot_auto_drvier | TODO |
| deepbot_description | deepbot_project/deepbot_description | BSD |
| deepbot_driver | deepbot_project/deepbot_driver | TODO |
| deepbot_gazebo | deepbot_project/deepbot_gazebo | TODO |
| deepbot_line_follower | deepbot_project/deepbot_line_follower | MIT |
| riki_msgs | deepbot_project/deepbot_msgs | BSD |
| deepbot_nav | deepbot_project/deepbot_nav | TODO |
| deepbot_object_detect | deepbot_project/deepbot_object_detect | TODO |
| deepbot_object_plate | deepbot_project/deepbot_object_plate | TODO |
| deepbot_openvino | deepbot_project/deepbot_openvino | TODO |
| deepbot_racecar | deepbot_project/deepbot_racecar | TODO |
| deepbot_yolo_detection | deepbot_project/deepbot_yolo_detection | TODO |
| rikibot_yolov5 | deepbot_project/rikibot_yolov5/rikibot_yolov5 | APLv2 |
| yolov5_ros_msgs | deepbot_project/rikibot_yolov5/yolov5_ros_msgs | TODO |
| imu_calib | imu_calib | BSD |
| opencv_apps | opencv_apps | BSD |
| robot_localization | robot_localization | BSD |
| voice_assistant | voice_assistant | TODO |

初始快照共 23 包：BSD 8、GPLv2 2、MIT 1、APLv2 1、TODO 11；APLv2 为原文，未擅自规范化成另一授权声明。未枚举到单独 LICENSE/COPYING/NOTICE 文件，只能证明导出副本缺少，不能推断车载或上游原仓库也没有。

具体文件头进一步说明包内并非一刀切：

- camera_umd/uvc_camera/include/uvc_cam/uvc_cam.h:4—16：Morgan Quigley 版权及 GNU GPL 第 2 版或后续版本声明；package.xml 仅写 GPLv2，保留二者原文。
- camera_umd/jpeg_streamer/include/mongoose.h:1—10：Sergey Lyubka 版权与包含版权/许可通知的权限条款；不要由该包 BSD 字段覆盖该文件声明。

D 盘未解包项目资料（排除 .venv/.git/cache）共 76 文件，12 ZIP、1 RAR；未找到裸 package.xml 或独立 LICENSE。两份 MCU 源 ZIP 是另一套固件源码，不是缺失的 ROS 工作区。

- robot-x4.zip：666 成员；Libraries/CMSIS/License.doc 为 39936 字节二进制文档，仅记录哈希，未声称已解析条款。55 个 C/H 文件前 75 行有版权/许可匹配。
- robot_x4_bsp_0606.zip：983 成员；112 个 C/H 文件前 75 行有版权/许可匹配。Bsp/RingBuffer.h 出现 Arduino 版权及 LGPL 2.1 或以后版本；另有 ARM/ST 文件头。
- 精确归档相对路径、成员、哈希与匹配行在 audit.json.d_drive。没有恢复系统镜像、展开嵌套安装器或执行固件。

A 的必要补取若增加授权原件，最终审查将列为新增证据；本文件当前为第一轮快照盘点。

## 最终补充 — 2026-10-13

A整理完成后重新检查：23包字段仍按上述原文保留。现已包含以下实际文件，故“未导出独立许可证”仅描述第一轮快照，不能继续用于描述最终副本：

- `vehicle_ws/legacy_packages/deepbot_line_follower/LICENSE.md`；SHA-256 `7d2c5104e5a11abad0bce518f3ace60dd073adaedab88e6657ff2f123dbaad1c`。
- `vehicle_ws/legacy_packages/deepbot_yolo_detection/darknet/LICENSE`；SHA-256 `2021f0b8d6426fbf9a2f0126f1e8a7d3b1d7027c871b9979fa2543b9557000c4`。
- `vehicle_ws/legacy_packages/rikibot_yolov5/yolov5/LICENSE`；SHA-256 `7fa7e56c0db71105f4b59a6a0ac40225eb059876f85cd380383f7d7a066e68be`。
- `vehicle_ws/NOTICE.md`；SHA-256 `de0d638f95e86817085a5bdc7fbf07417b5e00b109e36d119921955cea7f1b6a`。
- `vehicle_ws/src/imu_calib/LICENSE`；SHA-256 `2463d922533cabc906b905e9e79aa594f1ab7cee925c6da35b6945ff4051e8fc`。
- `vehicle_ws/src/robot_localization/LICENSE`；SHA-256 `baec7235ef687e028567622e5ef59d5184c70dc03d609039d9ca33ce0695da5a`。
- `vehicle_ws/src/uvc_camera/COPYING`；SHA-256 `edaef632cbb643e4e7a221717a6c441a4c1a7c918e6e4d56debc3d8739b233f6`。

uvc_camera/COPYING为本机Git发行版提供的完整GPLv2文本，来源由LICENSE_TEXT_SOURCE.json单独注明。内嵌yolov5/LICENSE确为GNU GPL v3，外层APLv2字段仍在；Darknet实际正文标题YOLO LICENSE，不能概括成统一BSD/MIT。11个TODO字段尚未明确；保留用户公有目标，不增加虚假授权。
