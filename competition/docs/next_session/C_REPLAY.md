# C｜首段直道＋普通弯道：停车后立即回放

2026-10-13。依据 [本轮计划](../team/NEXT_SESSION_PLAN.md) 与当前 B/C CLI 源码核对；本卡命令待真实数据到位执行。本轮只准备操作卡，不连车、不改算法、不训练、不重跑大测试。无需独立静止20秒关卡。

**先分清四件事：**采集方法 `acquisition_method=joystick`（实际用手柄移动）；B 数据语义 `mode=visual_only, role=manual_visual`（没有已核实动作标签）；首批划分 `split=development`（按整会话，非相邻帧随机拆分）；C 回放描述 `--dataset-role visual_sequence`（真实移动视觉序列）。C 参数只支持 `synthetic/static/visual_sequence/unknown`，不接受 `manual_visual` 或 `development`。当前 B 校验已允许上述手柄组合。后续另采未参与调参的整会话才作 validation；一旦用于修改算法，须记录 consumed。

## 1　乙交导出包，丙运行回放

在 Windows 项目根目录执行，按提示填写 A 已核实的 Python（含 NumPy/Pillow）、本机仓库外 DATA_ROOT 和完整会话路径。与 B 保持同一布局：`DATA_ROOT/raw/SESSION` 为只读原始会话，`DATA_ROOT/derived/SESSION_export` 为导出包，`DATA_ROOT/replay/` 存新回放；传输到本机后保留该布局。已有 B 导出包直接复用，新输出不覆盖。

```powershell
$cPython = (Read-Host 'A已核实的Python解释器绝对路径').Trim('"')
if (-not (Test-Path -LiteralPath $cPython -PathType Leaf)) { throw '解释器不存在，请核对A提供的路径。' }
$cDataRoot = (Read-Host '本机仓库外DATA_ROOT绝对路径').Trim('"')
$cSession = (Read-Host '已正常结束的完整会话绝对路径（DATA_ROOT/raw/SESSION）').Trim('"')
foreach ($cPath in @($cDataRoot, $cSession)) {
    if (-not (Test-Path -LiteralPath $cPath -PathType Container)) { throw "目录不存在：$cPath" }
}
$cDataRoot = (Resolve-Path -LiteralPath $cDataRoot).ProviderPath
$cSession = (Resolve-Path -LiteralPath $cSession).ProviderPath
$cRepo = (Get-Location).Path.TrimEnd('\')
if ($cDataRoot -eq $cRepo -or $cDataRoot.StartsWith($cRepo + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'DATA_ROOT必须在仓库外。' }
if ((Split-Path -Parent $cSession) -ne (Join-Path $cDataRoot 'raw')) { throw '会话路径应为DATA_ROOT/raw/SESSION，请核对数据根目录。' }
$cSessionId = Split-Path -Leaf $cSession
$cRun = Get-Date -Format yyyyMMdd_HHmmss_fff
$cExport = Join-Path $cDataRoot "derived/${cSessionId}_export"
$cReplay = Join-Path $cDataRoot "replay/${cSessionId}_$cRun"
if (-not (Test-Path -LiteralPath $cExport)) {
    & $cPython -B -m competition.data_tools export --session "$cSession" --output "$cExport"
    if ($LASTEXITCODE -ne 0) { throw 'B导出未通过：先查看错误与quality.json，不重复覆盖输出。' }
}
& $cPython -B -m competition.data_tools inspect --export "$cExport"
if ($LASTEXITCODE -ne 0) { throw 'B导出质检未通过：交B/A定位该问题。' }
& $cPython -B -m competition.perception.replay --root "$cExport" --manifest "$cExport/camera_frames.jsonl" --dataset-role visual_sequence --output "$cReplay"
Get-Content "$cReplay/summary.json"
Invoke-Item "$cReplay/overlays"
```

`--root` 是 **B 导出包**，不是仓库根、原始会话根或 images 子目录；清单保留两路角色，勿再用目录模式猜 high/low。数据量正常时预期生成 records、diagnostics、provenance、overlays 和 summary；C 不输出速度。B export/inspect 退出2须读质量错误；C 退出2表示存在输入拒绝，空清单报错。C 退出0只表示处理完成，可能所有道路无效或部分有效但识别错误。B/C 输出同属派生批次，不改原 manifest。

## 2　原图与叠加图对照看，不只看有效率

先核对 B `quality.json` 的两路 frames/decoded、public_frame_count/public_omissions，再核对 C input_count/processed/rejected/by_camera。B 公共清单会省略不合格时间/身份记录，坏帧仍留在 samples/raw；不要把“已进入 C 的帧”当全部采集帧，也不要改用目录模式绕过时间拒绝。

每路抽首/中/尾，再补弯道入弯—弯中—出弯及修正前后连续小段。不要只挑绿线好看的帧。`diagnostics.jsonl` 的 camera_id、replay_frame_seq 标识相机/源帧；**叠加文件名按 input_index 六位编号**（如 index=12 对应 000012.png），不是 frame_seq。用同 input_index 的 provenance.original_record 和 original_image_ref 找到 B 原图，并结合 samples/exclusion_reasons、events 确认手柄修正段。修正保留，不当自主成功或训练动作标签。

逐例记“会话＋相机＋源帧/时间段、正确/错误/不可判定、现象”，重点同时保留有效且正确、有效但错误、无效拒绝三类。绿线应贴所见黑色引导线；offset 右正是图像含义，不是已验证控制方向。quality 是行支持比例，不是准确率或净空。

## 3　按具体失败决定下一段

| 所见 | 归类与下一步 |
|---|---|
| 缺一路、坏图、时钟拒绝/配对异常 | 交B/A查对应日志；修正后补该直道/弯道段，不先调视觉阈值 |
| 白路充满低位视野而被拒、连续黑线在弯中丢失 | 保留两路同段原图，检查当前40%—90% ROI、双侧蓝边要求、线宽/连续性；补同弯不同偏位 |
| valid=true，却跟阴影、黑杂物或错误分支 | 优先记误识别；补正常与阴影/杂物相邻片段，不靠提高valid比例判断改善 |
| 分叉/环岛明确无效 | 可是正确的歧义拒绝；补入口—交汇—出口连续视角与路线说明，不强取一条黑线 |
| 普通路段像素路径经目视可用 | 转采有区别的锥桶、分叉/环岛、横杆各状态、车库；不重复堆直道，不宣称可自主行驶 |

## 收到首段后 C 具体做什么

先按上述源帧键建立小批人工对照，定位“错跟线”和“本可识别却拒绝”的原因；当前没有完整真实数据，**没有真实准确率结论**。获总控扩展代码范围后，仅改被数据证实的问题：例如分相机 ROI/可见边界条件、局部亮暗分离或曲线连续性；不先放宽所有阈值，不在一张图堆特例。保留修改前后同段结果，并用新采的同类片段检查是否减少错误而增加漏检/误识别；窄阴影像黑线的已知风险单独核对。

YOLO 的判断按任务：先核实现有模型真实类别/输出；道路像素失败先定位视野与几何，不因丢线就训练检测器。若锥桶/人行道/横杆等所需类别缺失，或在多段正反例上持续漏检/误检，才提出最小标注与模型比较方案，交总控决定。检测框不等于横杆可放行或整车净空，单段直道/弯道不足以验收这些任务；本次不训练。
