# MotionForge AI｜AI 自动生成 MG 动画视频

**先完整提取参考视频的中英文，再选择在线表格逐段改稿或提供完整脚本；只替换文字，保留原视频的全部视觉效果。**

Extract the full bilingual timeline, choose editable-sheet changes or a complete script, and replace text while preserving the reference visuals.

## 两种改稿方式

每次任务先完整查看参考视频，按时间段列出全部中文、英文和文字出场范围，再进入一种方式。已明确选定方式时不重复确认。

| 方式 | 你需要做什么 | 输出哪些内容 |
| --- | --- | --- |
| A：在线表格逐段修改 | 在真正可在线编辑的表格中，修改想替换的中文或英文 | 只输出实际修改的片段；不连续的片段分别交付 |
| B：直接提供完整脚本 | 发来整篇新稿，无须自己拆镜头或标时间码 | 从参考第0帧起按顺序使用全部新稿，输出到最后使用文字的退场与效果结束 |

A模式中，留空表示保留原文；明确选择“删除”才删字。中英文分别判断，只改中文时保留原英文。若新文字与原文相同，不生成无变化的“修改版”。

B模式必须使用完整脚本；参考容量不足时说明剩余内容与冲突，不自行截稿、默认只做20秒、重复镜头、改变速度或强塞成不可读小字。长句的可读容量和真实退场边界仍需逐镜检查，机械选段通过不代表视觉已验收。

## 保持不变的内容

文字之外的原场景、镜头运动、元素、动画、转场、配色、材质和风格均保留。新稿主题变化不授权重新生成画面。新文字沿用参考的动效机制，不能将复杂动画简化为普通淡入淡出。

| 项目 | 默认处理 |
| --- | --- |
| 画幅与尺寸 | 沿用参考，不默认竖版、裁切或拉伸 |
| 帧率与节奏 | 沿用参考，不加速、循环或延长 |
| 声音 | 按导出片段同步保留原音轨 |
| 字体与样式 | 优先匹配参考；缺失时说明差异并确认替代 |
| 额外要求 | 本次明确指定的配音、静音、字体、尺寸等要求叠加执行 |

## 直接使用

1. 点击本页 **Code → Download ZIP** 并解压，或克隆原仓库。
2. 将 `skills/remake-reference-video` 整个目录安装到你的 AI 工具支持的 Skills 目录；已有安装请更新这个目录。
3. 上传参考视频并发出指令：

```text
使用 MotionForge AI（remake-reference-video）。
先按时间段提取附件参考视频全部中文和英文，
然后让我选择在线表格逐段改稿，或直接提供完整脚本。
只替换文字，保留全部原动效、转场、元素、动画和风格。
```

如果已经决定提供全文，可以直接说：

```text
使用 MotionForge AI，我选完整脚本模式。
先提取完整参考的双语时间轴，再从第0帧起依次放入下面全部文案。
只替换文字，其他沿用原片，输出到最后文字退场效果结束。

新脚本：
（在此粘贴完整文案）
```

A模式需要实际可写入、保存并重新读取的在线表格服务，例如已连接的 Google Sheets。Markdown表格、截图、静态网页或本地Excel不能冒充在线表格；若当前环境缺少连接，AI应明确说明。

## 运行环境

这是供具备视频/图片查看与代码执行能力的 AI 使用的 **Skill 工作流**，GitHub仓库本身不是在线视频制作网站。AI负责识别、映射、画面处理与视觉验收，辅助脚本负责确定选段、检查文字、合成、导出和技术验证。

需要 Python 3.11+、FFmpeg/ffprobe，以及依赖：

```bash
python3 -m pip install -r requirements.txt
ffmpeg -version
ffprobe -version
```

公开仓库不包含私人三极字体。只换字任务应提供实际匹配参考或用户明确认可的授权字体。现有 `font_setup.py` 可下载并验证 SIL OFL 1.1 授权的 Noto Sans CJK SC Bold；只有匹配参考或明确接受替代时才使用，许可与来源见 `assets/fonts/`。

## 主要文件

- [SKILL.md](skills/remake-reference-video/SKILL.md)：完整工作流程与交付规则。
- [intake-workflow.md](skills/remake-reference-video/references/intake-workflow.md)：双语提取、在线表格、全文输入及选段约定。
- [text-replacement.md](skills/remake-reference-video/references/text-replacement.md)：输入基线、A/B映射、选段任务与导出绑定格式。
- [motion-remake.md](skills/remake-reference-video/references/motion-remake.md)：五类动效拆解与只换字保留原则。
- [shot-contract.md](skills/remake-reference-video/references/shot-contract.md)：镜头与动效检查格式。
- `scripts/text_replacement.py`：逐语言改动比较、完整脚本映射、选段与导出约束检查。
- `scripts/video_pipeline.py`：抽帧、局部底片处理、文字合成、原声保留与验证。
- `scripts/export_ae.py`：导出AE文字层与关键帧构建脚本，声音跟随本次计划。
- `tests/`：已有渲染与错误输入验证。

## 验收边界

有可编辑原工程且AE实际可用时，优先替换原文字层。只有MP4时，原图层已经压平，需要局部去字、底片恢复和文字动效重建；不能据此保证任意参考片逐像素一致。

辅助脚本不会自动完成OCR、理解全文或证明所有非文字画面未变。选段、文字完整性和技术检查通过之后，仍须完整播放实际输出，逐镜比较文字、镜头、场景、元素、转场、可读性与声音。复杂三维或插件效果需要实际可用的合成能力；不能仅交JSX、提示词或静态图并称为成片。

本次更新沿用原仓库及内部调用名 `remake-reference-video`。
