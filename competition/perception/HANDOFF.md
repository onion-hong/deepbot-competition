# C 感知与离线回放交付 — 2026-10-13

已完成可执行模块；19 项离线测试通过；目录与逐帧清单各有 14 帧、28 条公共契约记录通过验证。没有连接车辆、启动相机/底盘、训练、发布速度、修改公共接口或提交 Git。成果为 **uncommitted**，代码/测试/接口 SHA-256 见最终批次 summary.json，不借用 A 的基线提交号冒充 C 代码版本。

## 实际改动

| 文件 | 实现 |
|---|---|
| road.py | NumPy 颜色分离、逐行白路/黑线候选、连续性/歧义拒绝、公共 road payload |
| replay.py | 目录/清单输入，解码/身份/时间校验，原图副本、JSONL、叠加图、失败摘要 |
| synthetic.py | 14 个确定性合成开发场景生成器 |
| requirements.txt | NumPy/Pillow，无 OpenCV/ROS/模型依赖 |
| ../tests/perception/test_perception.py | 19 项测试，临时文件限 C 测试目录，结束移除自身临时文件 |

读过原厂 auto_run.py 和修补版 factory_auto_run.py，没有导入/运行它们。新实现不复制黄色质心、P/D 增益、320×240 缩放或速度发布；原厂副本及署名保留。

## 算法与输出含义

不缩放原图。在 y=40%—90% 的 ROI 每约 1% 高度取一行：蓝色优势分离背景，白/低色差与暗像素形成道路候选；两侧必须看到蓝区，窄黑线两侧必须有白肩。要求至少 90% 行支持、连续缺失不超过 2 行、近远端有支持、相邻点斜率有限。参数完整保存在 PARAMETERS 与摘要，是开发启发式，未获现场验证。

多道路/多黑线（显著分叉、环岛交汇）、宽黑块、遮挡缺段、无黑线、无蓝边、过暗或急剧跳变拒绝；不选最大黑块，不延续上一帧。ROI 外或采样行之间的细分支可能漏检。双侧蓝边要求可能使低位近场白路充满画面时大量拒绝，等待真实图像再判断，未为合成数字放宽。

原点左上，x 右正、y 下正。参考点 `((width-1)/2, round((height-1)*0.70))`，目标 x 在参考 y 插值。`offset_px=target_x_px-reference_x_px`，右正，单位原图像素；path 从远到近排列。quality 是支持行比例，非正确概率/净空/行车许可。

按总控澄清：**road.valid 表示像素路径估计成立**，有效时输出 target/offset/path；无效时 null/null/[]。净空及行车许可由 A 单独检查。有效 reason 为 pixel_path_estimate_clearance_unverified；摘要始终 vehicle_clearance_verified=false、motion_permission=false。没有米制距离，也没有 detections/motion_request 空桩。

已知重要反例：窄深阴影与细黑色引导线可能像素相似，本算法会误识别；合成集明确保留该案例。蓝区也可能是蓝板/锥桶，不能仅凭颜色解释为可行驶边界。

## 输入、资产、身份与时间

目录模式递归读 JPG/JPEG/PNG，按文件名排序，必须显式指定 high/low，不猜采集时间或物理身份。physical_id=unverified-directory-*；source_stamp=null、source_clock=unknown，不用文件 mtime 冒充曝光时间。混合双路用清单，不能把同一目录读两次声称双摄像头。

清单每行必须为冻结 deepbot.offline/0.1.0 的 camera_frame，同一清单只含一个原始 session。复用 A 严格校验，拒绝重复键、非有限数、逃逸根目录的路径、帧重号、接收时间/源时间重复倒退、时钟/物理身份变化、同物理相机映射两角色。拒绝行完整写 provenance，不静默丢弃；该行不产生可用 road，下游不得复用旧结果。

文件用 Pillow 解码 RGB/L：JPEG/PNG 不是裸 BGR 内存，即使采集清单 encoding=bgr8，也不对已经 RGB 的解码结果再错换颜色。数组 API 另显式支持 bgr8→RGB。检查 uint8、尺寸、通道、格式及 EXIF 旋转；mono 可解码但因缺颜色信息输出 color_unavailable。保留原始分辨率。

输出创建独立 offline-replay-* session 和 perf_counter_ns 单调时钟；frame receipt 是实际离线加载后的回放接收时刻，road stamp 是计算后同域时刻。**原始记录完整保留在 provenance.original_record**，不重写原采集时间；清单原 frame_seq 和 source_stamp/source_clock 也保留在回放帧。不能跨 clock_id 相减，不能把回放耗时当车载延迟。

| 输出 | 解析方式 |
|---|---|
| records.jsonl | camera_frame 与 road 交替，供公共验证和下游读取 |
| images/ | 输入原图逐字节副本，核对 SHA-256；image_ref 相对这个新输出目录，独立可读 |
| provenance.jsonl | 原记录、原始相对路径、回放 frame_seq、原图哈希、输入拒绝原因 |
| diagnostics.jsonl | 候选像素、颜色覆盖、支持行数、未验证净空标记 |
| overlays/ | 橙色参考线、绿色候选、像素有效性，不是行车授权图 |
| summary.json | 数量/原因/逐相机统计、角色声明、参数、依赖与代码/测试/接口哈希 |

输出目录已存在即拒绝，文件不覆盖；空输入报错。逐帧输入被拒绝时 CLI 退出码 2；无输入错误时为 0（即便所有 road 无效）。complete 仅表示遍历结束，不是感知或比赛成功。中断可能留下无摘要的部分目录，需标不完整保留。不能从帧数自动推断场景覆盖。

## 复现入口与依赖

在项目根目录运行 PowerShell。已核对默认 Anaconda 与 bundled runtime 都没有 cv2；本实现直接用后者已有 NumPy/Pillow，未安装全局依赖。实际 Python 3.12.14、NumPy 2.3.5、Pillow 12.3.0；requirements 最低版本范围及车载 Python 3.8 尚未逐版本实测。

```powershell
$cPython = 'C:\Users\hongs\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $cPython -B -c "import sys,numpy,PIL; print(sys.executable); print(numpy.__version__,PIL.__version__)"
& $cPython -B -m unittest discover -s competition/tests/perception -p 'test_*.py' -v
& $cPython -B -m competition.interfaces.validate competition/perception/evidence/20261013_synthetic_04/records.jsonl
& $cPython -B -m competition.interfaces.validate competition/perception/evidence/20261013_manifest_01/records.jsonl
```

预期且已取得：19 tests OK，两批分别 OFFLINE_CONTRACT_OK records=28。日志/结果见 synthetic_04/tests.txt、verification.json。失败需检查类型、时钟、输入或算法，不放宽公共验证器。

新建一批（时间名避免覆盖）：

```powershell
$cBatch = 'competition/perception/evidence/local_' + (Get-Date -Format yyyyMMdd_HHmmss_fff)
& $cPython -B -m competition.perception.synthetic --output "$cBatch/input"
& $cPython -B -m competition.perception.replay --root "$cBatch/input" --camera-id low --dataset-role synthetic --output "$cBatch/replay"
```

清单入口已实际执行，同样使用新输出目录：

```powershell
& $cPython -B -m competition.perception.replay --root competition/perception/evidence/20261013_synthetic_04 --manifest competition/perception/evidence/20261013_synthetic_04/frames.jsonl --dataset-role synthetic --output "$cBatch/manifest_replay"
```

B 原始数据到位后更换 root/manifest，并如实使用 --dataset-role static 或 visual_sequence。manifest 要 camera_frame-only，不直接输入混合配对/事件清单。输出目前留 C 专属目录；B 会话 derived 写入需 B 协调。

## 测试、结果与任务输入样例

最终证据：evidence/20261013_synthetic_04 和 evidence/20261013_manifest_01。每批 14 输入、14 处理、0 输入拒绝，5 像素有效、9 无效。合理候选为直线、左右弯、适中阴影；第 5 个是故意保留的窄深阴影误识别。**5/14 不是准确率**；这些是实现中用过的开发场景，不是独立评估。

19 项测试及子场景覆盖符号、1280×720 原图坐标比例、阴影、无黑线、宽黑杂物、遮挡、分叉/环岛/双道路、断线/无蓝边、RGB/BGR/mono、错误 dtype、无旧路复用、可消费有效 road、解码/尺寸错误、禁止覆盖、路径穿越、身份/时间重复、混合 session、空输入、原时间与帧身份保留、整批契约及图像资产解析。

给 D/A 的真实输出样例：synthetic_04/mission_sample.jsonl，共 4 条（2 帧+2 road），同目录 images 可直接读取：

| frame_seq | 场景 | valid | offset_px | path 点数 | 使用边界 |
|---|---|---|---|---|---|
| 2 | 合成 Y 分叉 | false | null | 0 | 歧义，不任意选出口或继续旧路 |
| 9 | 合成右弯 | true | +4.5 | 60 | 图像右侧像素候选；A 仍检查独立行车条件 |

开发迭代未覆盖：01 的输出采用已被总控纠正的过度公共无效门控（其 input 仍是最终合成输入）；02 记录 NumPy 标量的 schema 失败；03 记录 Windows monotonic_ns 粗粒度重复帧时间；04 修复为标准浮点与高分辨率 perf_counter_ns 后整批通过。01—03 不是最终合格结果。

## 真实数据与尚未覆盖

已读 A 的 VEHICLE_HANDOFF.md 和 static_01/manifest.json。用户/A 确认 high=video0、low=video2，角色不能叫前/后摄；A 曾观察到 1280×720 流，但 JPEG 留样 high=0、low=0、complete=false。**本轮无真实原图可回放，真实静态回放和正式赛连续覆盖均未完成**。没有用聊天截图冒充原始720P或用旧黄线短测证明新场成功。

当前仅可能适用于：固定姿态、ROI 两侧蓝区可见、白路上单一连续细黑线、对比足够的直道/温和弯道，仍待真实验证。未实现锥桶绕行、逆时针环岛完整绕行/出口选择、计圈、横杆、人行道、车库/倒车能力。未测现场灯光/姿态分布、车载性能/期限、ROS 接入、双路同步、净空和运动闭环。

下一批由现场团队另获授权采，C 不操作设备：

1. 固定双路原图：直道中/左右偏位、左右弯远近、S 弯极值；支架视角与全场轮胎画面。
2. 正式连续路线：出库、三锥桶、逆时针环岛入口/绕行/出口、S 弯、人行道、车库；保留停止、倒车、纠正、遮挡与坏帧。
3. 分叉/交汇正对与斜对，窄/宽/深阴影、黑杂物、反光、褶皱、白路充满低位画面、蓝板/锥桶/背景混淆。
4. 横杆落下/抬起/运动/未知、人行道合法位置变化、车库左右偏位与倒车视野。后续完整两圈仍须分别覆盖两种落杆圈次。
5. 每会话记录角色、相机映射/配置、原始时间、事件；开发与冻结后独立评估分会话。像素线/道路边界标注与整车净空实测分开。

## A/B/D 对接

A：无需修改冻结 schema；road.valid 只管像素路径，净空/新鲜性/反馈/任务许可/唯一速度发布由 A 负责。正像素偏离不是已标定的角速度符号。后续地面几何需要相机姿态、标定、车辆轮廓及实测边界。

B：提供 camera_frame-only 清单与图像根；源时间缺失用 null/unknown。不能由 CameraInfo=0 或 CompressedImage.format 为空推定原图无效；解码尺寸/编码需明确。C 的回放输出自带原图副本。清单时间正常不能证明内容未冻结，仍需 B 的采集质量记录。

D：读取样例与原帧身份；缺失/无效新 road 不复用旧路。横杆、车库、目标类别尚未实现，不把空结果或不存在的检测当 clear。此交付不含实车部署许可。等待总控查收。
