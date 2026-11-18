# 标准动画计划

由执行任务的模型根据实际参考片生成此JSON，不要求用户填写。路径相对`plan.json`或使用绝对路径。脚本不自动理解自然语言、不自动推断时间轴；这些是Skill执行者的职责。

```json
{
  "version": 1,
  "source": {
    "frame_dir": "analysis/frames",
    "width": 720, "height": 1280,
    "fps": "30/1", "frames": 60
  },
  "plate": {"frame_dir": "clean_frames"},
  "output": {"width":1080,"height":1920,"fps":"30/1","background":[155,2,5]},
  "replacements": [
    {"id":"s1","start":0,"end":60,"source_cn":"原主标题","cn":"新的标题","en":"NEW TITLE","english_mode":"provided"}
  ],
  "layers": [
    {"id":"s1_cn","slot":"s1","language":"zh","role":"primary","text":"新的标题","font_size":130,"fill":[241,234,194],"tracking":0,"in":0,"out":60,"keys":[[0,360,630,0.15,0.15,0,1,0],[8,360,630,1,1,0,1,0]]},
    {"id":"s1_en","slot":"s1","language":"en","role":"primary","text":"NEW TITLE","font_size":26,"tracking":4,"fill":[241,234,194],"in":0,"out":60,"keys":[[0,360,740,1,1,0,0,0],[10,360,740,1,1,0,0.85,0]]}
  ]
}
```

上述仅演示结构，不代表新任务应该用红底、720×1280、30fps或两秒。从`prepare`的`media.json`复制本次解码源属性。

## 字段

- `source`是实际解码源的像素坐标系；`plate.frame_dir`是已经检查的无旧字底片，不填时沿用源帧（仅适合本来无须清字的情况）。所有帧目录必须完整连续命名为`f_000001.png`。
- `output`默认1080×1920并等比容纳。参考非竖屏时用`background`补边。输出帧率须与解码源一致；需要更改时先在`prepare --fps`规范化源帧，不能只改输出fps导致总时长漂移。
- `font`可省略以自动获取默认 Noto 字体；自定义时填`{"path":"font.ttf"}`，PostScript 名从字体读取。可另填 `postscript`，但必须与实际字体相符。支持单字体 TTF/OTF；TTC 应先选择并导出需要的 face。先检查cmap。
- `replacements`是完整新稿的内部对照，`cn`与`en`必须符合用户输入；英文为空时填空字符串，不能把“—”排到视频。`english_mode`区分provided、translated、none或keep。未变更原转场可填`preserve:true`，同时确保该段底片保留且无新字层。
- 一行一个层，多行用多个层。每个文字组按逻辑阅读顺序排列`primary`层（也用于逐字轨道），拼接后必须等于该组完整新稿；自动换行允许删除换行符对比。英文空格、数字、符号与大小写不能随意变。
- `echo`层只重复主稿，文本完整性核对不重复计数。每个层的`slot`必须指向真实文字组。
- `keys`每项为`[帧号,x,y,水平缩放,垂直缩放,顺时针角度,不透明度,模糊半径]`；坐标、字号、模糊半径、tracking都以源像素为单位。透明度0–1，缩放1为100%。关键帧线性插值；复杂缓动应采样成更密的关键帧。第一键必须等于该层`in`。
- `in/out`左闭右开，均为全片帧号；`out`允许等于总帧数，末关键帧必须小于`out`。有意跨镜头的转场可跨组边界，但须视觉检查。
- 颜色为RGB整数0–255，文字锚点为可见字形中心。

## 执行

```bash
python3 "$SKILL_DIR/scripts/video_pipeline.py" check-plan --plan "$JOB/plan.json"
python3 "$SKILL_DIR/scripts/video_pipeline.py" render --plan "$JOB/plan.json" --output "$JOB/final.mp4"
python3 "$SKILL_DIR/scripts/video_pipeline.py" verify --plan "$JOB/plan.json" --video "$JOB/final.mp4" --report "$JOB/validation.json"
```

脚本默认拒绝覆盖既有MP4，并用锁和临时文件保护输出。确认确需改版时使用新文件名或`--overwrite`；若被中断，先确认无旧进程再处理遗留锁，不要直接并发重跑同名输出。

验证工具仅核对计划文字、字体和技术指标。源内容识别、旧字清除、装饰保护、运动一致性与可读性必须由模型查看图片/视频确认。

包内`render/verify`实现默认无音轨路径。用户明确要求保留人声或音效时，先完成画面，再按其要求分离/混入相应音轨，并改用允许目标音轨的技术检查；不能全静音后声称满足保留人声的要求。

## 可选AE脚本

```bash
python3 "$SKILL_DIR/scripts/export_ae.py" --plan "$JOB/plan.json" --output "$JOB/ae_editable"
```

输出`Run_in_After_Effects.jsx`、独立底片和字体。JSX使用相同计划建立原生文字层与关键帧，保持素材相对位置。没有AE运行时仍先交MP4；脚本静态检查不等于AE实际执行、预览或渲染。有AE时运行脚本并另存新的工程，再按实际可用输出模板渲染，不能覆盖不相关工程。
