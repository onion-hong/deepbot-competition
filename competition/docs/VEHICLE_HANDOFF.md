# 现场接口交接（2026-10-13，本轮只读）

**最新状态（18:01:55北京时间）：原相机/查看器/master进程已不存在，11311不再监听，设备查询无占用；关闭原因未知，A未执行停止或重启。** 下方两路数据只描述17:57的有效观察窗，不能当作当前在线。18:01:17追加12秒JPEG留样失败（Connection refused），high/low均0帧、complete=false；不得称为真实采集成功，不再重连或补启动。

已核实环境：Ubuntu20.04.6 x86_64，ROS1 Noetic，roscpp/rospy1.17.0，Python3.8.10。A未启动/停止/重启相机、master或底盘。公共 deepbot.offline/0.1.0 字段保持冻结，以下是实际ROS映射与差异，不是未经协调的新schema。

| 角色（用户现场确认） | 当前设备 | 现有话题 | 类型 | 稳定USB路径 |
|---|---|---|---|---|
| 高位 high | /dev/video0 | /camera_high/image_raw/compressed | sensor_msgs/CompressedImage | /dev/v4l/by-path/pci-0000:00:14.0-usb-0:3:1.0-video-index0 |
| 低位 low | /dev/video2 | /camera_low/image_raw/compressed | sensor_msgs/CompressedImage | /dev/v4l/by-path/pci-0000:00:14.0-usb-0:2:1.0-video-index0 |

17:57:34—17:57:40被动观察6秒：high180帧（30.022Hz）、low181帧（30.000Hz），361/361均可解码1280×720×3；本窗无header.seq跳号或来源时间重复/回退。仅保存元数据/哈希，未保存JPEG。实时CompressedImage.format为空，两路header.frame_id都为camera；不要据此拒绝所有原始数据或认定为同一物理相机。存原始format，解码成功后另记解码编码bgr8；相机身份由topic+USB映射确认。两路序列号相同，by-id冲突，不能作为唯一键。

camera.cpp在cam->grab之前用ros::Time::now赋header.stamp，属于主机ROS时钟，**不是硬件曝光时刻或双路硬同步**。两路CameraInfo实际width/height为0，K/P全0，未标定；不能从CameraInfo取图像尺寸或生成米制几何。旧640×480 YAML不能当当前720P标定。

17:52graph没有/raw_odom、/odom、/imu/data_raw、/imu/data、/sonar或/cmd_vel发布者；18:01master也不在。不能为了记录器就绪启动底盘。B应区分visual_only（反馈可空、不能导出驾驶动作标签）与demonstration（必要反馈缺失拒绝就绪）。源码默认：raw_odom为nav_msgs/Odometry，imu/data_raw为sensor_msgs/Imu，sonar为std_msgs/Float32，cmd_vel为geometry_msgs/Twist。bringup配置由raw_odom和imu/data融合成odom；本轮未运行验证。sonar数值由int16/10得到，量纲未证实，不能标米；实测运动符号/比例/停止能力也未知。

目录deepbot_auto_drvier实际包名为deepbot_auto_driver，目录deepbot_msgs实际包名为riki_msgs，不按目录名编import。已导出DriverMode/Servo和vision_msgs0.0.2生成定义/MD5；标准CompressedImage MD5为8f7a12909da2c9d3332d540a0977563f。车上实际导入OpenCV4.11.0、NumPy1.23.5；另有apt OpenCV4.2.0，不能只看dpkg就断言Python运行库。

数据与报告根目录：主项目的 `vehicle_snapshot_20261013_readonly/`（代码Git忽略，只读工程证据）。`raw/01_inventory.json` 保存系统/graph/USB，`raw/03_stream_probe.json` 保存短窗逐帧时间/哈希/尺寸，`FILE_MANIFEST.json` 保存车载文件及本地副本哈希，`MESSAGE_DEFINITIONS.json` 保存实际生成消息的MD5与递归全文。

总控已协调：B独占competition/data_tools、competition/tests/data_tools；C独占competition/perception、competition/tests/perception；A不改这些目录。无Git提交时可按独占范围先离线开发，版本明确null/uncommitted+源文件哈希。B存储格式在本模块定义，转换器对接冻结公共契约。不要使用被忽略的tests/data。

12秒JPEG留样未完成，失败目录 `vehicle_snapshot_20261013_readonly/camera_sessions/20261013_static_01` 保留完整失败标记与空索引，不能提供给C当图像集。6秒成功观察的质量汇总在CAMERA_OBSERVATION_QUALITY.json。无原始JPEG不阻止B/C/D合成/已有离线资料开发。等待总控查收B交付后再安排无运动接入，本轮不继续相机/底盘操作。

Git初始基线已完成：`cd3d33415bbe4b753c1340a333ac6bc51e0c3927`（原51项，不含本次快照或其他模块新成果）。最终报告、差异建议、给B摘要和待执行测量卡分别在快照目录00—03文档。快照含本机设备信息且被Git忽略；在其他工作树需只读引用主项目该目录，不复制进代码仓库。

后续离线集成只设一个由A维护的入口，待B/C/D各自HANDOFF查收后实现：B导出camera_frames与会话质量/时钟信息 → C回放输出road → A检查公共契约、来源/新鲜性和停止仲裁，保存最终请求与原因，不连接ROS发布器。当前只是入口设计，没有新增适配程序。road.valid表示像素候选满足感知判据；车辆净空、运动授权和安全通过由A另外判断，不因米制净空未标定就强迫所有像素候选invalid，也不能因road.valid就放行车辆。D高级事件（圈数、横杆、倒库阶段等）必须有明确来源与证据；C道路输出不自动提供这些能力。离线合成事件标注synthetic，不能混为现场识别。
