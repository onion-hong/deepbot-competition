# 来源副本（只读参考）

精确来源、字节数和 SHA-256 见 ../docs/PROVENANCE.json，复制时逐字节保留。原始来源目录及所有历史日志均未覆盖。厂商代码保留原署名/注释，授权范围尚未核实，不附加自有开源许可证；相关权利仍归原作者。原先仅本地归档，现按用户要求共享项目，公开访问不代表获得了统一的开源许可。

这些源码不是 Python 包，不批量导入、不自动测试。original/racecar/train.py 会顶层训练；original/auto_driver/params.cfg 会顶层生成；data_collect.py 会删旧目录；历史 replay 测试顶层执行且依赖缺失的运行布局；transport 测试启动 ROS master 和虚拟串口驱动。只允许新 tests/offline 入口。
