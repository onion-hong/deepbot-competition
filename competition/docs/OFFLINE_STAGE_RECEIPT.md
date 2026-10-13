# 2026-10-13 离线阶段集成收据

本页记录A在三模块HANDOFF完成后的本地版本归档，不是车辆运行验收。共同父版本为 `7b5315d619c7bca37948f63bdf69a04b8806cc5b`；本页所属提交可用 `git log -1 --format=%H -- competition/docs/OFFLINE_STAGE_RECEIPT.md` 查询。公共接口仍为 `deepbot.offline/0.1.0`；B存储为 `deepbot.data/0.1.0`，D内部事件为 `deepbot.mission/0.1.0`。

| 模块 | 已交付能力 | 未完成的边界 |
|---|---|---|
| B data_tools | 双路会话、独立时间/身份、原始记录、反馈配对审计、纠正排除、导出/回读；ROS只订阅入口 | 真实ROS双路记录器未验收；无IMU/sonar通用采集、断电恢复；visual_only不生成驾驶标签 |
| C perception | 原分辨率像素道路候选、歧义拒绝、camera_frame清单/目录回放、原图与诊断输出 | 无真实原图验证；road.valid不是净空或运动许可；窄深阴影存在误识别；无高级目标/赛段识别 |
| D mission | 有序任务账本、计圈/停车/等杆/倒库证据约束、回放和故障锁存 | 公共请求恒stop、stop_required恒true；真实高级事件生成、轨迹跟踪、倒库控制、执行回执仍缺 |

**验证依据：** 总控独立复跑接口13+B26+C19+D32，共90项通过。原始收据为仓库本地 `比赛实施方案_20261013/审查附件/总控阶段验收_20261013.json`。A读回该收据并逐一核对其中23份源码/测试SHA-256，全部一致；本归档不重复运行90项。A另核对冻结接口全部5文件与D交付依赖哈希一致。归档的32份模块源码、配置、说明、测试的原始字节哈希见 `OFFLINE_STAGE_SOURCE_HASHES.json`；Git可按属性归一化文本换行，不改工作区字节。

**6帧贯通入口：** `competition/tests/offline/verify_data_perception.py`，复制自总控根目录本地 `比赛实施方案_20261013/审查附件/verify_data_perception.py`，只将PROJECT路径的parents[2]改为parents[3]以匹配目录层级，其余行为不变。B SessionWriter→export_session→C replay→公共validate_stream；总控第三批收据为6帧、12条公共记录、4条有效道路、2条无效道路、0驾驶示范样本、PASS。A将新入口另跑一次，结果见本地 `competition/tests/offline/outputs/archive_20261013/ROOT_ACCEPTANCE.json`。使用显式合成时钟，不是实时采集性能，也未接入A运动仲裁或D高级事件。第一批时钟碰撞失败保留；不拿重跑覆盖失败。

```powershell
# 仓库根目录；$offlinePython须指向装有NumPy/Pillow的已核对解释器。
# 当前本机已验证的解释器路径见各HANDOFF；默认python不保证依赖齐全。
$offlinePython = (Get-Command python).Source
$batch = 'competition/tests/offline/outputs/pipeline_' + [guid]::NewGuid().ToString('N')
& $offlinePython -X utf8 -B 'competition/tests/offline/verify_data_perception.py' --output $batch
```

正式入口随本次代码提交版本化，安装NumPy/Pillow后可从工作树执行；总控原始收据仍保留在本地审查附件。输出目录必须全新，已被outputs规则忽略，执行失败不覆盖旧批次。各模块单独测试/合成入口也已版本化。

**纳入与排除：** 按 `OFFLINE_STAGE_FILES.txt` 精确提交37项：32份B/C/D交付文件（含3个原README改动）、1份贯通脚本、根.gitignore及本页/清单/源码哈希3份归档文件。盘点时5个输出/证据目录共1816文件、32,232,514字节只加忽略，未删除。D的PROVENANCE.json含本机解释器路径和历史Git状态，原样留本地并精确忽略；SHA-256为 `2317ca7be78bb398661b24cafe1491f0f00a3f848eeee7bff12de73fd25a9901`。HANDOFF中的uncommitted/旧HEAD是交付时刻历史，不改写成当时已提交；当前代码版本以本次Git提交为准。说明中的本机示例路径保留用于复现，不含凭据；本次不推送。

**下一关：** 仍需A的运动控制器/唯一速度仲裁与停车保护接入，C/A真实高级事件和几何来源，以及分别获准的静态记录、基础测量、分段与完整两圈验证。不是“只差实车测试”。本轮未SSH、启动设备、运行模型或扩展业务代码。
