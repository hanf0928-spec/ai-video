
# 漫画转漫剧流水线详解

本文详细说明 [backend/app/pipelines/manga2anime/pipeline.py](../backend/app/pipelines/manga2anime/pipeline.py) 中 `Manga2AnimePipeline.run()` 的 11 个阶段。

## 1. Load（加载）

- 输入：PDF / 长条漫 / 多图 / zip
- 实现：`loader.load_pages()`
  - PDF → `pdf2image.convert_from_path` 按页渲染
  - 长条漫 → 以 `max_h=2400` 为单位切割
- 输出：`List[Path]` 页面图像

## 2. Panel Detection（分格检测）

实现：`panel_detect.detect_panels()`

优先级：
1. **YOLOv8**（需在 `data/models/panel_yolov8.pt` 放置权重）
2. **传统 CV**：阈值 → 形态学闭运算 → 轮廓 → 最小面积过滤

输出：`[{page,order,bbox,image_path}]`，按阅读顺序排好。

## 3. OCR（文字识别）

实现：`ocr.ocr_panel() + group_bubbles()`

- 默认 `PaddleOCR`（中文）；可切换 `EasyOCR`。
- 相邻的 OCR 片段按几何邻近性合并为气泡。

## 4. Character Consistency（角色一致性）

实现：`character.build_character_bank()`

- 使用 `lbpcascade_animeface.xml` 检测动漫脸（也可换 `anime-face-detector`）
- HSV 颜色直方图作为简易 embedding
- 贪心聚类，相似度 ≥ 0.4 归入同一角色
- 每个角色裁出 ≤ 5 张参考图，供后续绑定 LoRA / IP-Adapter

> 生产环境建议替换为 CLIP / ArcFace 等深度特征。

## 5. Script（LLM 分镜脚本）

实现：`script.panels_to_storyboard()` → `LLMAdapter.panels_to_script()`

系统提示词要求返回严格 JSON：
```json
{
  "title": "...",
  "characters": [...],
  "shots": [
    {"index": 0, "scene": "...", "camera": "...", "action": "...",
     "dialogue": "...", "speaker": "...", "emotion": "neutral", "duration": 4}
  ]
}
```

LLM 不可用时回退到基于 OCR 的简单脚本。

## 6. Image Preparation（首帧准备）

当前实现：**复用原漫画格图像作为视频首帧**。

> 若需要先做风格迁移（漫画 → 动画），可在此处插入 ComfyUI 工作流调用（例如 SDXL + IP-Adapter）。

## 7. I2V Generation（图生视频）

实现：`get_video_adapter(backend).generate(req)`

两个后端：
- `HailuoAdapter` → POST `/video_generation` → poll `/query/video_generation`
- `SeedanceAdapter` → POST `/contents/generations/tasks` → poll

失败时回退到 `image_to_video()`（静态图生成占位视频）。

## 8. TTS（配音）

实现：`TTSAdapter.synthesize()`（MiniMax `t2a_v2`）

- 每个 shot 的 `dialogue` 独立合成
- 支持 `emotion` 参数
- 使用 FFmpeg `mux_audio` 把音频挂到对应 shot 视频

## 9. Concat（拼接）

`concat_videos()` 使用 FFmpeg `concat` filter 重编码合并所有 shot 视频。

## 10. BGM（背景音乐）

实现：`pick_bgm(dominant_emotion)` + `mix_audio()`
- `data/bgm/` 中按情绪关键字匹配文件名（如 `sad_piano.mp3`）
- BGM 音量 0.25，旁白 1.0

## 11. Subtitle（字幕）

- `shots_to_srt_entries()` 根据 duration 推算时间戳
- `build_srt()` 生成 SRT
- `burn_subtitle()` 使用 FFmpeg `subtitles` filter 硬编码字幕

## 进度回调

每个阶段调用 `self._p(stage, progress, msg)`，Celery worker 把进度写回 `Job` 表，前端通过 `WS /api/jobs/ws/{job_id}` 实时拿到。

## 失败回退策略

| 阶段 | 失败 | 回退 |
|------|------|------|
| 分格 | 无面板 | 整页作为一个 panel |
| OCR | 识别失败 | 空字符串，shot 无对白 |
| 角色 | 未检出 | 跳过，不影响后续 |
| LLM | API 错误 | 规则化简易脚本 |
| I2V | API 失败 | 静态图生成视频 |
| TTS | 失败 | 跳过配音，仅视频 |
| BGM | 无素材 | 跳过 |
| 字幕 | 空对白 | 跳过烧录 |
