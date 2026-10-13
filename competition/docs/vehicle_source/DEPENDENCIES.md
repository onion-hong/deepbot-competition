# 编译范围与外部依赖

版本基准：只读现场Ubuntu20.04.6、ROS1 Noetic，roscpp/rospy1.17.0。Windows整理不证明这些源码可在任意Noetic版本编译。`src`内7包没有重复package name；旧目录deepbot_msgs的真实包名是riki_msgs。其余16包只能按legacy清单分别恢复，不能整体拖进src后宣称支持。

| 核心包 | 本工作区依赖 | 外部编译/运行依赖与用途 |
|---|---|---|
| riki_msgs | 无 | catkin、message_generation/runtime、std_msgs、geometry_msgs；16msg＋7srv |
| deepbot_driver | riki_msgs | roscpp/rospy、std/geometry/sensor/nav_msgs、tf/tf2/tf2_ros、serial；Servo.msg实际生成，不复制devel包装器 |
| uvc_camera | 无 | roscpp、sensor_msgs、nodelet、pluginlib、camera_info_manager、image_transport、Boost thread/system、libv4l-dev；Linux V4L2源码 |
| imu_calib | riki_msgs | cmake_modules、roscpp、sensor_msgs、Eigen3、pkg-config、yaml-cpp；串口核心启动不自动运行校准 |
| robot_localization 2.6.8 | 无 | diagnostic_msgs/updater、eigen_conversions、geographic_msgs、geometry/nav/sensor/std_msgs、std_srvs、message_filters/generation/runtime、nodelet、roscpp、roslint、tf2/geometry/ros、xmlrpcpp、Eigen3、yaml-cpp、GeographicLib |
| deepbot | riki_msgs，启动另依赖driver/localization/description | roscpp/rospy、geometry/nav/sensor/std_msgs、tf；新serial入口额外用imu_filter_madgwick和tf2_ros；保留deep_base旧rosserial代码但不在新入口启动 |
| deepbot_description | 无 | catkin；URDF/STL资源包。显式视觉展示才需roslaunch、robot_state_publisher、rviz；不是碰撞/净空标定 |

核心依赖的准确声明以各package.xml为准，原厂声明与修整后声明都写入PACKAGES.json。准备一台单独Linux构建机时可依据`rosdep check --from-paths src --ignore-src --rosdistro noetic`缺项使用`rosdep install`，但安装需要联网/管理员权限，**本次没有执行，也不要求在小车上执行**。已安装Noetic的主机通常仍需serial、imu-filter-madgwick、camera-info-manager、image-transport、cmake-modules、robot-localization的构建依赖。不能把Windows pip安装当ROS依赖安装。

构建命令见vehicle_ws/README.md。默认`CATKIN_ENABLE_TESTING=OFF`因为厂商测试bag/外部数据不附带；这不跳过任何已执行失败测试。Linux验证应分开记录：catkin配置、编译、install、消息生成、加载路径，再到另获授权的节点/设备验证。没有新建空消息，也没有删除运行时停车保护。

旧包外部依赖包括：Gazebo/URDF相关模拟资源、ar_track_alvar、旧导航/激光/深度相机驱动、rosserial、OpenCV与cv_bridge、vision_msgs、自带Darknet/CUDA/CUDNN、PyTorch/torchvision、OpenVINO、TensorRT等。若只准备核心7包，不安装这些legacy依赖。旧YOLO/OpenVINO的版本约束、下载脚本、模型路径未经新环境适配；默认不执行下载/训练/启动脚本。

开发机WSL：A首次只读枚举返回E_ACCESSDENIED；总控后来查到注册的Ubuntu24.04但启动返回HCS_E_SERVICE_NOT_AVAILABLE。两者都不是可用的Ubuntu20.04/Noetic编译环境；未再次启动WSL、安装系统或改服务。
