# zh / zh-cn Podcast Audio Data Report

> Generated: 2026-04-29
> Data path: `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/raw_data/{zh,zh-cn}`

---

## 1. Overview

### Raw Data (All Files on Disk)

| Metric | zh | zh-cn |
|--------|------|-------|
| Podcast count | 3,580 | 25,407 |
| Podcasts with audio downloaded | 3,580 (100%) | 5,797 (22.8%) |
| Total FLAC files | 116,049 | 228,228 |
| Total data size (FLAC) | ~4.27 TB | ~7.04 TB |
| Estimated total duration | ~48,872 hours | ~84,418 hours |
| Split files (_N suffix) | 23,564 | 60,619 |

### Valid Episodes — download=done + JSON with text

> Filter: download_state.json status=done, FLAC exists on disk, transcription JSON exists with non-empty text segments.

| Metric | zh | zh-cn | Total |
|--------|------|-------|-------|
| Valid episodes | 100,206 | 172,444 | **272,650** |
| Valid segments (utterances) | 10,293,979 | 17,638,318 | **27,932,297** |
| Total duration | 44,810.6h (1,867.1d) | 70,290.5h (2,928.8d) | **115,101.1h** |
| Total size | 3.97 TB | 6.20 TB | **10.17 TB** |

---

## 2. Manifest File Format (JSONL)

路径: `/inspire/qb-ilm/project/embodied-multimodality/zhikang/raw_data/manifest_{lang}.jsonl`

仿照 [Emilia](https://huggingface.co/datasets/amphion/Emilia-Dataset) 数据集格式，**每个 segment (utterance) 一行**，可直接按 `start_time`/`end_time` 从源 FLAC 截取对应片段。

| 文件 | 条目数 | 大小 |
|------|--------|------|
| `manifest_zh.jsonl` | 10,293,979 | 5.5 GB |
| `manifest_zh-cn.jsonl` | 17,638,318 | 9.2 GB |

### 字段说明

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | 唯一标识, 格式 `{lang}_{episode_hash[:12]}_{split_idx}_{seg_idx}` |
| `wav` | string | 源 FLAC 相对于 `{lang}/` 目录的路径 |
| `text` | string | 转写文本 |
| `start_time` | float | 片段起始时间 (秒), 用于截取 |
| `end_time` | float | 片段结束时间 (秒), 用于截取 |
| `duration` | float | 片段时长 (秒) |
| `language` | string | `zh` 或 `zh-cn` |
| `podcast_hash` | string | 所属播客目录名 |
| `episode_hash` | string | 所属 episode 的 base hash |
| `speaker` | string | (可选) 说话人标识 `spk_{id}`, 无 speaker_id 时省略 |

### 示例

```json
{
  "id": "zh_ff8dc21a03f2_00_00000",
  "wav": "001a83ab7189302c842ebc38b388ae41/audios/2026/ff8dc21a03f22022ed33d15b408e6124.flac",
  "text": "Alright, 欢迎收听最新一集的嘤嘤播来记，我是小叶。",
  "start_time": 0,
  "end_time": 5.34,
  "duration": 5.34,
  "language": "zh",
  "podcast_hash": "001a83ab7189302c842ebc38b388ae41",
  "episode_hash": "ff8dc21a03f22022ed33d15b408e6124",
  "speaker": "spk_0"
}
```

### 后续切分用法

```python
# 按 manifest 从源 FLAC 截取 utterance 级别音频片段
import json, torchaudio

with open("manifest_zh.jsonl") as f:
    for line in f:
        entry = json.loads(line)
        wav, sr = torchaudio.load(f"zh/{entry['wav']}",
                                  frame_offset=int(entry['start_time'] * sr),
                                  num_frames=int(entry['duration'] * sr))
        # save wav as individual utterance file
```

---

## 3. Directory Structure

```
{zh,zh-cn}/
├── manifest_{lang}.jsonl   # segment 级 manifest
├── {url_hash}/
│   ├── metainfo.json          # 播客元信息 + episode 列表
│   ├── download_state.json    # 每个音频的下载状态 (可选)
│   └── audios/
│       ├── 2025/
│       │   ├── {audio_hash}.flac          # 单文件 episode
│       │   ├── {audio_hash}.json          # 转写标注
│       │   ├── {audio_hash}_1.flac        # 分段音频 (>30min 切分)
│       │   ├── {audio_hash}_1.json
│       │   └── ...
│       ├── 2026/
│       └── unknown/
```

---

## 4. Audio Properties (torchaudio 实测)

使用 `torchaudio 2.3.1+cu118` 实际加载验证（各随机抽样 100 个文件）：

| Property | zh | zh-cn |
|----------|------|-------|
| **Sample Rate** | 24000 Hz (100%) | 24000 Hz (100%) |
| **Channels** | 1 (mono, 100%) | 1 (mono, 100%) |
| **Format** | FLAC | FLAC |
| **Load dtype** | float32 (normalized) | float32 (normalized) |
| **Errors in 100-sample** | 0 | 0 |

### Duration Stats (200-sample)

| | zh | zh-cn |
|--|------|-------|
| Min | 36.9s | 3.6s |
| Max | 3,599.9s (~60min) | 3,599.4s (~60min) |
| Avg | 1,516s (~25.3 min) | 1,332s (~22.2 min) |

> 长音频被切分为多段，每段最长 ~3,000s (50min)，以 `_1`, `_2`, ... 后缀命名。

---

## 5. Metainfo Format (metainfo.json)

```json
{
  "parent_url": "https://feeds.soundon.fm/podcasts/xxx.xml",
  "parent_chash": "5a4ac138b14738337cd8de29083b97c3",
  "parent_url_hash": "001a83ab7189302c842ebc38b388ae41",
  "language": "zh",
  "title": "大叔野球543",
  "author": "山姆/阿傑/斯文/果蠅",
  "episodes": [
    {
      "audio_url": "https://track.fstry.me/.../rssFileVip.mp3",
      "audio_url_hash": "ff8dc21a03f22022ed33d15b408e6124",
      "publish_year": "2026",
      "transcription": "",
      "tag": ["baseball", "棒球", "中職"]
    }
  ]
}
```

---

## 6. Download State Format (download_state.json)

```json
{
  "ff8dc21a03f22022ed33d15b408e6124": {
    "status": "done",
    "file_name": "2026/ff8dc21a03f22022ed33d15b408e6124.flac",
    "file_size_bytes": 43359124,
    "content_type": "audio/mpeg",
    "http_status": 200,
    "final_url": "https://filesb.soundon.fm/.../xxx.mp3",
    "attempt_count": 1,
    "last_error": null
  }
}
```

### Download Status Summary

| | zh | zh-cn |
|--|------|-------|
| Total entries | 103,408 | 287,574 |
| **done** | 103,219 (99.8%) | 192,724 (67.0%) |
| **failed** | 189 (0.2%) | 94,850 (33.0%) |

---

## 7. Transcription Format (audios/\*/\*.json)

每个 FLAC 文件对应一个同名的 JSON 转写文件：

```json
{
  "file": "/absolute/path/to/audio.flac",
  "generation_time": 2579.52,
  "segments": [
    {
      "start_time": 0,
      "end_time": 11.23,
      "text": "[Music]"
    },
    {
      "start_time": 11.23,
      "end_time": 19.31,
      "text": "Hello 大家好，歡迎收聽大叔野球543...",
      "speaker_id": 0
    }
  ]
}
```

Segment 字段: `start_time`, `end_time`, `text`, `speaker_id` (可选)

### Transcription Coverage

| | zh | zh-cn |
|--|------|-------|
| Total episodes (done) | 103,219 | 192,724 |
| **With valid transcription** | 100,206 (97.1%) | 172,444 (89.4%) |
| Missing or empty transcription | 3,013 (2.9%) | 20,280 (10.6%) |

### Speaker Statistics

Speaker ID 为 **episode 内局部编号**（从 0 开始），不同 episode 的 spk_0 是不同的人。

| | zh | zh-cn |
|--|------|-------|
| Total segments | 10,293,979 | 17,638,318 |
| **有 speaker_id** | 9,847,063 (95.7%) | 16,871,091 (95.7%) |
| **缺失 speaker_id** | 446,916 (4.3%) | 767,227 (4.3%) |
| Episodes 有 speaker | 99,670 | 158,438 |
| Episodes 无 speaker | 256 | 2,585 |
| 多人对话 episode | 50,988 (51.1%) | 65,584 (41.4%) |
| 单人 episode | 48,682 | 92,854 |

### Non-Speech Tags

转写中包含非语音标记（如 `[Music]`、`[Speech]`），以 `[...]` 格式标注。

**主要 tag 分布：**

| Tag | zh | zh-cn |
|-----|------|-------|
| `[Music]` | 275,050 (60.4%) | 568,979 (73.7%) |
| `[Speech]` | 72,173 (15.8%) | 31,935 (4.1%) |
| `[Human Sounds]` | 32,111 (7.0%) | 73,084 (9.5%) |
| `[Silence]` | 28,698 (6.3%) | 39,537 (5.1%) |
| `[Environmental Sounds]` | 24,858 (5.5%) | 32,462 (4.2%) |
| `[Noise]` | 12,642 (2.8%) | 14,556 (1.9%) |
| `[Unintelligible Speech]` | 5,573 (1.2%) | 5,696 (0.7%) |
| `[Hard Speech]` | 3,712 (0.8%) | 3,788 (0.5%) |
| 其他 (20+ 种) | ~1,642 | ~1,641 |
| **Total tags** | **455,659 (4.43%)** | **771,678 (4.38%)** |

**Speaker_id 缺失与 Tag 的关系：**

| | zh | zh-cn |
|--|------|-------|
| 缺失 speaker_id 的 segment | 446,916 | 767,227 |
| 其中为 non-speech tag | 446,898 (**100.0%**) | 767,186 (**100.0%**) |
| 其中为正常文本 | 18 (0.0%) | 41 (0.0%) |

> **结论**：speaker_id 缺失几乎完全由非语音标记导致。正常语音 segment 的 speaker_id 覆盖率接近 100%。缺失形式为 JSON 中 `speaker_id` 字段不存在（key absent），非值为空。

---

## 8. Data Sources

**zh (繁体中文, 台湾为主):**
- SoundOn (soundon.fm) 为主
- 部分 RSS feed

**zh-cn (简体中文, 大陆为主):**
- 喜马拉雅 (ximalaya.com)
- 小宇宙 (xyzcdn.net / xiaoyuzhoufm.com)
- Anchor.fm / Spotify
- 荔枝FM (lizhi.fm)
- 各类独立播客平台

---

## 9. Key Findings

1. **采样率统一**: 所有音频已统一转码为 **24000 Hz mono FLAC**，可直接用于训练。

2. **zh-cn 下载不完整**: 77.2% 的播客目录没有音频文件，33% 的 episode 下载失败。

3. **有效数据**: 过滤 done + 有转写后，**272,650 个 episode**、**27,932,297 个 segment**，共 **115,101 小时 / 10.17 TB**。

4. **Manifest (JSONL)**: 以 segment 为粒度，每条包含 `wav` 路径 + `start_time`/`end_time` 时间戳，可直接截取生成 utterance 级音频文件，对齐 Emilia 数据集格式。

5. **长音频切分**: 部分 episode 被切分为多段 (`_1`, `_2`, ...)，manifest 中按 split_idx 区分，同一 episode 的不同分段各自展开为独立 segment 条目。
