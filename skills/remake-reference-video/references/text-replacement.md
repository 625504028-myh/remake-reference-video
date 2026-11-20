# 双语提取、选段与只换字契约

先完整查看参考片、提取所有中文和英文，再冻结 `timeline.json`。以下均为执行者内部文件，用户只需选择修改表格或提供整篇新稿；工具不执行 OCR 或自然语言理解。

## 1. 冻结原文基线

```json
{
  "version":1,"extraction_complete":true,
  "source":{"path":"reference.mp4","fps":"30/1","frames":300,"width":1080,"height":1920},
  "slots":[
    {"id":"s01","start":0,"end":60,"cn":"原中文一","en":"FIRST"},
    {"id":"s02","start":60,"end":120,"cn":"原中文二","en":"SECOND"},
    {"id":"s03","start":150,"end":210,"cn":"原中文三","en":"THIRD"}
  ]
}
```

- 原片和所有素材路径相对所在 JSON。基线的 `cn/en` 均必填；确实没有该语言才填空字符串，不能将漏提取当成没有英文。
- 帧号为完整参考片的零基、左闭右开区间。`start/end` 必须包含文字入场、稳定段、退场、叠影和拖尾。纯抽象转场不作为遗漏文本槽位。
- 一组原文字连续重复快闪时，可提为一个逻辑槽位，区间包含全部出现；文字层以主层与 echo 层区分重复，不要求新稿反复写同一句。
- 存在跨镜头动效依赖时，可另填 `edit_window:[safeStart,safeEnd]`，它必须包含完整槽位。A 路线合并重叠窗口；不能借依赖范围新增文字修改。
- `usable:false` 仅用于原片确实不能承接正文的非正文槽位，不能用于跳过不喜欢的镜头。B 按首个可用槽位开始分配。
- `extraction_complete` 仅为人工检查声明，脚本不能证明提取完整。保存后不得用“修改后”文案覆盖原基线。

```bash
python3 "$SKILL_DIR/scripts/text_replacement.py" digest --baseline "$JOB/timeline.json"
```

将返回的 SHA256 写进下面请求的 `baseline_sha256`。每轮改稿重新保存请求文件；原基线保持不变。可在 `source.sha256` 额外记录原视频文件校验值。

## 2A. 用户修改表格

```json
{
  "baseline_sha256":"填入实际校验值",
  "mode":"manual",
  "edits":[
    {"slot_id":"s01","cn":"修改后的中文","en":""},
    {"slot_id":"s03","delete":["en"]}
  ]
}
```

缺失、null、空白或仅空格的字段均保留原语言；删除必须列入 `delete`。不能把空白当删除。与原文完全相同不生成任务；换行或非空文字中的空格变化视为排版修改。中英文独立比较，仅改英文不得重写中文。未知 ID 或同一 ID 重复编辑会报错。

例中只生成 s01 与 s03 两个独立选段，s02 不输出。重叠依赖窗口自动合并；不跨越未修改空隙。确需把相邻区间合并，可显式设 `merge_adjacent:true`，不添加新的转场。

## 2B. 用户提供整篇文案

```json
{
  "baseline_sha256":"填入实际校验值",
  "mode":"full-script",
  "units":[{"id":"u1","cn":"第一句新稿"},{"id":"u2","cn":"第二句新稿"}],
  "assignments":[
    {"unit_id":"u1","slot_ids":["s01"],"cn_parts":["第一句新稿"]},
    {"unit_id":"u2","slot_ids":["s02"],"cn_parts":["第二句新稿"]}
  ]
}
```

先由执行者理解全文并拆成完整语义单元，再自行分配；不让用户标时间码。所有单元必须依次使用一次，槽位从首个可用槽位连续选取。一个单元跨多个槽位时，用多个 `cn_parts`，拼接后须等于原文；只允许调整换行，不能漏句、重复句或改数字。

英文未提供时保留各槽位原英文。用户提供英文时，在 unit 填 `en`、assignment 填对应 `en_parts`；明确删英文则在 assignment 填 `delete:["en"]`。用户明确允许自动配英文时，先完成翻译核对并记录，再写入请求；工具不会自行翻译。

输出固定从原片第 0 帧开始，到最后使用槽位完整退场结束。上例输出 `[0,120)`，不是自动截成 20 秒。全部文案都必须容纳；`copy_policy` 只能为 `full`。超过源片容量、跳槽、倒序、遗漏单元均报错。若后一个未采用标题已在最后退场结束前进入画面，也会报错，须重新审视槽位边界或文案分配，不能混入旧标题交付。

## 3. 可选明确覆盖

默认只换字，保持原画面、帧率、尺寸、字体风格和原音轨。用户另有明确要求时才在请求中添加：

```json
{
  "audio":{"mode":"mute"},
  "font":{"path":"user-provided.ttf","postscript":"实际字体名称"},
  "output":{"width":1080,"height":1920}
}
```

音频支持 `preserve/mute/replace/mix`。后两者必须先生成真实的替换/混合音频文件，再填写 `{"mode":"mix","path":"approved_mix.wav","start":0}`；不可仅改模式就声称完成混音。原片无音轨时 preserve 的结果仍无音轨。尺寸覆盖必须是正偶数；帧率变更须先明确规范化并重新提取基线，不得靠改输出 fps 改变时长。

## 4. 生成任务与绑定渲染

```bash
python3 "$SKILL_DIR/scripts/text_replacement.py" plan \
  --baseline "$JOB/timeline.json" --request "$JOB/request.json" --output "$JOB/jobs.json"
```

输出包含冻结文件校验值、各 job 的源片起止帧、实际修改列表和保留策略。A 无实际修改时 jobs 为空，不制作无意义新视频。不要手工改 jobs；变更请求后生成新文件。

为每个 job 创建独立分析目录和渲染计划，并写一个契约包装文件：

```json
{"version":1,"jobs_file":"jobs.json","job_id":"job-001","reference_media":"job-001/analysis/media.json"}
```

按照 job 的 `start_seconds/duration_seconds` 运行 `prepare`；`plan` 帧号减去 `source_start` 后从 0 计数。设置 `replacement_contract` 指向包装文件，`motion_manifest` 指向 `mode:text-replace` 的五类动效清单。两者必须绑定，不能只做选段检查而遗漏动效检查。

渲染计划的 `replacements` 只列实际变化的槽位，保留原稳定 ID，并填写新 `cn/en`。未修改语言放进 `preserve_languages:["en"]` 或 `["cn"]`；其原文字保留在底片中，不得又叠一个相同文字层。删除语言填空字符串且不建新层。`production` 填 `{"mode":"text-replace","preserve_nontext_visuals":true,"font_policy":"source"}`；用户明确提供字体时用 `provided` 并指向实际字体。

默认 `audio` 填 `{"mode":"preserve","path":"原参考视频绝对路径","start":源片起点秒数}`，不是裁出的无声底片。替换/混合音频则指向请求记录的实际文件，从 0 开始。

```bash
python3 "$SKILL_DIR/scripts/text_replacement.py" check \
  --contract "$JOB/replacement_contract.json" --plan "$JOB/plan.json" \
  --report "$JOB/replacement_validation.json"
```

检查会重新计算选段，拒绝基线被改、额外片段、漏改、新增未经选择的中英文层、场景重制及不符要求的音频/尺寸。它不证明视觉相同；仍需核对每个变化区间、非文字元素和切点附近画面。
