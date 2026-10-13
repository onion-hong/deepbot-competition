# 外置资产及未闭合的历史功能

源码与模型/运行数据分开。SOURCE_INVENTORY.json记录首次快照来源SHA和每个纳入/排除理由；SUPPLEMENT_INVENTORY.json及TARGETED_SUPPLEMENT_INVENTORY.json记录两次限定源码补取。外置模型的已知哈希另见MODEL_HASHES.json；没有哈希的历史资产不编造版本。

## 不随公有源码提交

- pt/pth/bin/weights等模型权重和OpenVINO成对xml/bin；包括源码目录中名字容易被误当配置的卷积权重。只保留已有哈希和文件相对位置。未经验证的网上同名模型不能替代。
- 图片/视频采集、训练/测试数据、bag、PGM地图、pbstream、缓存、devel/install/build、目标文件/动态库、用户凭据和本机私有配置。
- robot_localization与opencv_apps的部分测试引用外部bag/图像包；保留测试源和test launch，默认不开CATKIN_ENABLE_TESTING。测试源码完整不代表测试数据完整。
- legacy原始导航launch可能引用缺失的riki/xtrobot旧包名或厂商外部驱动；旧模型路径常是/home/deepbot。历史入口保留原貌并在CATKIN_IGNORE外部隔离，不能按原launch直接启动整车。
- 扩展名为.ipynb的演示笔记未补取；未采集字节的外部目录符号链接不跟随。它们不参加核心构建。历史脚本可能执行rm -rf、下载模型、发速度或访问相机，文件名含test也不能直接运行。

## 恢复步骤（待后续授权，本轮不执行）

1. 根据实际要用的单一legacy包，先审查CMake、launch、Python顶层和依赖图；不要移除整个legacy目录的CATKIN_IGNORE。
2. 从团队已授权且可溯源的原始文件取得模型/数据，复制到新的外部资产目录。对MODEL_HASHES.json列出的模型做SHA-256比对；缺失/不符就停止，不能下载同名文件冒充。
3. 将新配置显式指向外部资产，不覆盖原厂模型、标定或历史数据。记录文件哈希、模型类别顺序、预处理和推理库版本，再离线验证。
4. 已附deepbot_description真实URDF和STL，不再缺该几何资源；其尺度/安装位姿仍需测量。没有因缺资源而造空URDF或简化mesh。

D盘4份工控机恢复ZIP只读列目录，均为分卷partclone压缩分区，没有可直接取出的package.xml/URDF。没有解压/挂载整盘镜像或提取用户home。固件源码/刷写材料也未混入ROS工作区，实际已装MCU版本仍未知。
