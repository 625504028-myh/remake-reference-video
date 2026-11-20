# 只换字任务的动效清单

新 A/B 流程先使用 `text-replacement.md` 生成选段与 replacement_contract，再建立本清单。`mode` 必须为 `text-replace`；`copy_units` 在此模式不使用，文字核对统一由冻结基线与 replacement_contract 执行。

每个镜头必须覆盖选段中的连续帧，包含 text、camera、scene、elements、transition 五类。每项写 observed、implementation，并引用真实文字层 layer_ids 或本地素材 artifact_ids；不存在的类别为空列表并在 absent 说明。保留场景也要记录，不能因不修改就不检查。

`scene_treatment` 使用 `preserved`（包括实景与业务场景），填写 preserve_reason 和 preserved_artifact_ids，指向真实原片或底片证据。artifacts 的 kind 可为 source_media、scene_asset、build_source、project、review。禁止 rebuilt/generated。`copy_ids` 使用本任务实际修改槽位 ID，而不是全文语义单元 ID；一个变化跨镜头时可重复引用。

```json
{
 "version":1,"mode":"text-replace","reference_media":"analysis/media.json",
 "requested_window":{"start":0,"duration":2},"frames":60,"fps":"30/1",
 "artifacts":[{"id":"original","path":"reference.mp4","kind":"source_media","description":"完整原参考片"}],
 "plate":{"frame_dir":"clean_frames"},
 "shots":[{"id":"shot1","in":0,"out":60,"copy_ids":["s01"],
  "scene_treatment":"preserved","preserve_reason":"仅清除已选中的中文，保留原英文与全部画面",
  "preserved_artifact_ids":["original"],
  "effects":{
   "text":[{"observed":"标题逐字进场","implementation":"同节奏新中文字层","layer_ids":["s01_cn"]}],
   "camera":[],
   "scene":[{"observed":"原业务场景","implementation":"保留原片像素","artifact_ids":["original"]}],
   "elements":[],"transition":[]},
  "absent":{"camera":"原镜头固定","elements":"无独立装饰","transition":"本示例无切换"}}]
}
```

以上只是结构示例，必须依据本次原片重写观察、时间与图层。根节点 `plan.motion_manifest` 指向此文件；`plan.replacement_contract` 也必须同时绑定。`check-plan/render/verify` 均运行对应检查。完整解码检查和逐镜视觉验收仍必需，机械通过不证明动效相同。

## 旧版 MG 重制兼容格式

以下仅保留旧计划解释，不适用于当前 A/B 只换字流程。除非用户另行明确要求重制场景，不得切换此模式。

### 旧版镜头与动效执行清单

用于 `motion-remake` 模式；只换字任务可选。由执行者看完参考片、制定计划并完成场景素材后生成，不要求用户填写。文件记录“观察到什么→如何实现→实际文件/图层”，不能以一列“完成”代替证据。

## 时间窗口

```bash
python3 "$SKILL_DIR/scripts/video_pipeline.py" prepare \
  --video "$JOB/reference.mp4" --job "$JOB/analysis" \
  --start 0 --duration 20 --step 0.1
```

`--start`、`--duration` 单位为秒；省略时从开头处理至片尾。先按选定帧率归一化，再将起点和时长分别对齐到最近帧。请求超出源片时报错，不循环、不补黑。`media.json.window` 同时保留请求秒数与实际起止帧；29.97 等帧率的 20 秒可能无法恰好表示，必须记录实际时长，误差最多半帧。需要严格整数秒时，先选择合适的输出帧率并明确记录变更。

原片时间码由 `window.start_frame + 局部帧号` 计算；`plan.json` 与下面的所有镜头、文字层只使用窗口内从 0 开始的帧号。不能用全片帧数冒充前 20 秒。

## 清单格式

以下演示一个 1 秒窗口，不代表实际任务只有一个镜头或这些特效。先按本次参考片补全全部镜头与五类特效，并替换示例文件。

```json
{
  "version": 1,
  "mode": "motion-remake",
  "reference_media": "analysis/media.json",
  "requested_window": {"start": 1, "duration": 1},
  "fps": "10/1",
  "frames": 10,
  "copy_policy": "prefix",
  "copy_units": [
    {"id":"u1","cn":"新品上线","en":"NEW ARRIVAL","status":"used","slot_ids":["s1"]},
    {"id":"u2","cn":"下一段文案","status":"deferred","slot_ids":[]}
  ],
  "artifacts": [
    {"id":"scene1","path":"assets/scene1.png","kind":"scene_asset","description":"按新稿制作的产品卡片"},
    {"id":"builder","path":"build_scene.py","kind":"build_source","description":"实际生成逐帧场景底片的脚本"}
  ],
  "plate": {"frame_dir":"rebuilt_frames","builder_artifact":"builder"},
  "shots": [{
    "id":"shot1","in":0,"out":10,"copy_ids":["u1"],
    "scene_treatment":"rebuilt",
    "semantic_match":"新产品卡片承接新品上线的信息",
    "effects": {
      "text":[{"observed":"标题缩放入场","implementation":"原时长内重分配关键帧","layer_ids":["s1_cn"]}],
      "camera":[{"observed":"卡片推近","implementation":"构图与比例变化已烘焙到底片","artifact_ids":["builder"]}],
      "scene":[{"observed":"居中产品卡片","implementation":"用新稿对应卡片替换内容","artifact_ids":["scene1","builder"]}],
      "elements":[],
      "transition":[]
    },
    "absent":{"elements":"原镜头无独立装饰元素","transition":"此示例窗口在稳定段内结束"}
  }]
}
```

- `reference_media` 指本次 `prepare` 输出；请求窗口、源帧目录、帧数和帧率必须与实际渲染计划相同。
- `copy_policy` 默认 `full`，要求全文使用、不接受 `deferred`。只有用户允许“能用多少用多少”时才设为 `prefix`；`copy_units` 按原稿顺序列出所有完整语义单元，`used` 必须是连续前缀，其余为 `deferred`。未采用内容不得悄悄挤进片尾；不能擅自把 `prefix` 当作删稿授权。
- `slot_ids` 指一次出现对应的 `plan.replacements`，可将一句拆成多个槽位后拼接逐字核对。参考片将同一句多次快闪时，改用 `slot_occurrences`，如 `[["s1"],["s3","s4"]]`：每个内层数组各自拼接成完整同一句，而不是将重复出现误算为新稿重复。两字段不能同时填写；同一槽位只能归属一个出现。文案首次出现顺序必须与原稿一致，后续重复依参考片节拍安排。选中文字逐字核对，允许换行。用户提供英文时填写 `en` 并逐字核对；只给中文而自动翻译时可省略单元的 `en`，翻译仍放入渲染计划接受常规检查。
- `shots` 必须无缝覆盖 `[0, frames)`。同一文案跨镜头时可在多个镜头的 `copy_ids` 中重复引用；分镜不得改变文案次序。
- 每镜头必须含 `text/camera/scene/elements/transition` 五类；每个观察到的效果写清参考动作、实现方式，并指向真实图层或文件。确实不存在的类别填 `[]`，并在 `absent` 解释。不能把“没做到”记作“原片没有”。
- 图层引用必须存在并与镜头时间相交。非文字类动效必须引用实际场景/合成文件，不能只指向标题缩放层。文件引用必须存在且非空；`kind` 支持 `scene_asset/build_source/project/review`。动画素材、关键帧图像或无字片段可作为 `scene_asset`。
- `scene_treatment` 为 `rebuilt/generated/preserved-abstract`。前两者须有实际场景素材、语义对应说明；只保留与业务无关的抽象背景时使用最后一项并填写 `preserve_reason`。原片全为与业务无关的抽象图形时，可以所有镜头都保留，但必须逐镜写出理由；不能以此绕过真实业务场景的重制。
- `plate.frame_dir` 必须是渲染器实际使用的、完整连续的 `f_000001.png` 底片。场景重制由实际脚本或工程先完成；清单不负责生成动画。只要存在 `rebuilt/generated` 场景，就必须提供底片生成脚本/工程，并拒绝直接把原帧目录或内容完全相同的复制目录当作新底片。所有镜头均为有理由保留的抽象背景时，可使用已有底片，不强制生成无意义的场景替换。

## 接入与验收

在 `plan.json` 根节点加入：

```json
"motion_manifest": "shot_manifest.json"
```

MG 重制必须接入此字段，使 `check-plan`、`render`、`verify` 自动检查；旧版换字计划未填时仍可运行。也可显式检查：

```bash
python3 "$SKILL_DIR/scripts/motion_contract.py" check \
  --manifest "$JOB/shot_manifest.json" --plan "$JOB/plan.json" \
  --report "$JOB/shot_validation.json"
```

通过仅代表机械检查通过：窗口、时间轴、所选文案及引用文件一致。文件存在不证明它已真正被合成，也不证明观察没有遗漏、动效相似、字可读或画面有创意。执行者仍须逐镜核对最终成片，重点看五类特效、每个切点前后帧与新画面的语义对应；不得把报告中的通过当作视觉复刻已验收。
