# en-us Podcast Audio Data Report

> Generated: 2026-04-29
> Data path: `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/raw_data/en-us`

---

## 1. Overview

### Raw Data (All Files on Disk)

| Metric | en-us |
|--------|-------|
| Podcast count | 3,529 |
| Podcasts with audio downloaded | 3,529 (100%) |
| Total FLAC files | 185,936 |
| Total data size (FLAC) | ~8.20 TB |
| Estimated total duration | ~90,780 hours |
| Split files (_N suffix) | 62,066 |

### Valid Episodes — download=done + JSON with text

> Filter: download_state.json status=done, FLAC exists on disk, transcription JSON exists with non-empty text segments.

| Metric | en-us |
|--------|-------|
| Valid episodes | 145,683 |
| Valid segments (utterances) | 26,424,704 |
| Total duration | 90,780.1h (3,782.5d) |
| Total size | 7.66 TB |

---

## 2. Manifest File Format (JSONL)

路径: `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/raw_data/manifest_en-us.jsonl`

仿照 [Emilia](https://huggingface.co/datasets/amphion/Emilia-Dataset) 数据集格式，**每个 segment (utterance) 一行**，可直接按 `start_time`/`end_time` 从源 FLAC 截取对应片段。

| 文件 | 条目数 | 大小 |
|------|--------|------|
| `manifest_en-us.jsonl` | 26,424,704 | 14 GB |

### 字段说明

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | 唯一标识, 格式 `{lang}_{episode_hash[:12]}_{split_idx}_{seg_idx}` |
| `wav` | string | 源 FLAC 相对于 `en-us/` 目录的路径 |
| `text` | string | 转写文本 |
| `start_time` | float | 片段起始时间 (秒), 用于截取 |
| `end_time` | float | 片段结束时间 (秒), 用于截取 |
| `duration` | float | 片段时长 (秒) |
| `language` | string | `en-us` |
| `podcast_hash` | string | 所属播客目录名 |
| `episode_hash` | string | 所属 episode 的 base hash |
| `speaker` | string | (可选) 说话人标识 `spk_{id}`, 无 speaker_id 时省略 |

### 示例

```json
{
  "id": "en-us_10f25268dc12_01_00000",
  "wav": "0007c926b1b7770b65a46b3d3c642659/audios/2025/10f25268dc129bd69a85ac3ce4341415_1.flac",
  "text": "There is no controversy in the science. There is none.",
  "start_time": 0,
  "end_time": 27.66,
  "duration": 27.66,
  "language": "en-us",
  "podcast_hash": "0007c926b1b7770b65a46b3d3c642659",
  "episode_hash": "10f25268dc129bd69a85ac3ce4341415",
  "speaker": "spk_0"
}
```

### 后续切分用法

```python
# 按 manifest 从源 FLAC 截取 utterance 级别音频片段
import json, torchaudio

with open("manifest_en-us.jsonl") as f:
    for line in f:
        entry = json.loads(line)
        wav, sr = torchaudio.load(f"en-us/{entry['wav']}",
                                  frame_offset=int(entry['start_time'] * sr),
                                  num_frames=int(entry['duration'] * sr))
        # save wav as individual utterance file
```

---

## 3. Directory Structure

```
en-us/
├── manifest_en-us.jsonl   # segment 级 manifest
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

使用 `torchaudio 2.3.1+cu118` 实际加载验证（随机抽样 100 个文件）：

| Property | en-us |
|----------|-------|
| **Sample Rate** | 24000 Hz (100%) |
| **Channels** | 1 (mono, 100%) |
| **Format** | FLAC |
| **Load dtype** | float32 (normalized) |
| **Errors in 100-sample** | 0 |

### Duration Stats (200-sample)

| | en-us |
|--|-------|
| Min | 56.2s |
| Max | 3,497.5s (~58.3min) |
| Avg | 1,861.8s (~31.0 min) |

> 长音频被切分为多段，每段最长 ~3,600s (60min)，以 `_1`, `_2`, ... 后缀命名。

---

## 5. Metainfo Format (metainfo.json)

```json
{
  "parent_url": "https://foodintegritynow.org/?feed=podcast",
  "parent_chash": "7339c9fe9d4ea84dbe3349e85f80a72a",
  "parent_url_hash": "0007c926b1b7770b65a46b3d3c642659",
  "language": "en-US",
  "title": "Food Integrity Now",
  "author": "Carol Grieve'",
  "episodes": [
    {
      "audio_url": "https://media.blubrry.com/foodintegritynow/content.blubrry.com/foodintegritynow/Kelly_Ryerson_Interview_Final_Show.mp3",
      "audio_url_hash": "a29be2e8a4f7bdede1f795a20a923146",
      "publish_year": "2026",
      "transcription": "",
      "tag": ["Featured Shows", "Learn About GMO's", ...]
    }
  ]
}
```

---

## 6. Download State Format (download_state.json)

```json
{
  "a29be2e8a4f7bdede1f795a20a923146": {
    "status": "done",
    "file_name": "2026/a29be2e8a4f7bdede1f795a20a923146.flac",
    "file_size_bytes": 43085073,
    "content_type": "audio/mpeg",
    "http_status": 200,
    "final_url": "https://content.blubrry.com/foodintegritynow/...mp3",
    "attempt_count": 1,
    "last_error": null
  }
}
```

### Download Status Summary

| | en-us |
|--|-------|
| Total entries | 163,649 |
| **done** | 151,020 (92.3%) |
| **failed** | 12,629 (7.7%) |

---

## 7. Transcription Format (audios/\*/\*.json)

每个 FLAC 文件对应一个同名的 JSON 转写文件：

```json
{
  "file": "/absolute/path/to/audio.flac",
  "generation_time": 1782.58,
  "segments": [
    {
      "start_time": 0,
      "end_time": 7.33,
      "text": "[Music]"
    },
    {
      "start_time": 7.33,
      "end_time": 13.09,
      "text": "You're listening to Food Integrity Now with your host, Carol Gravay.",
      "speaker_id": 0
    }
  ]
}
```

Segment 字段: `start_time`, `end_time`, `text`, `speaker_id` (可选)

### Transcription Coverage

| | en-us |
|--|-------|
| Total FLAC files with download=done | 185,932 |
| **With valid transcription** | 176,869 (95.1%) |
| Missing JSON | 6,078 (3.3%) |
| Empty transcription | 2,985 (1.6%) |

---

## 8. Data Sources

**en-us (英语, 美国为主):**
- Buzzsprout (buzzsprout.com) — 886 podcasts
- Anchor.fm / Spotify — 565 podcasts
- FeedBurner (feeds.feedburner.com) — 166 podcasts
- Omny Studio (omnycontent.com) — 134 podcasts
- Loyal Books (loyalbooks.com) — 92 podcasts
- Simplecast (simplecast.com) — 57 podcasts
- Podbean (podbean.com) — 51 podcasts
- Megaphone (megaphone.fm) — 51 podcasts
- RedCircle (redcircle.com) — 49 podcasts
- Fireside (fireside.fm) — 37 podcasts
- 其他: Pinecast, Transistor, Castos, Blubrry, Libsyn, Captivate, PodPoint 等

---

## 9. Key Findings

1. **采样率统一**: 所有音频已统一转码为 **24000 Hz mono FLAC**，可直接用于训练。

2. **下载完整度很高**: 100% 的播客目录有音频文件，92.3% 的 episode 下载成功 (done)，仅 7.7% 失败。

3. **有效数据**: 过滤 done + 有转写后，**145,683 个 episode**、**26,424,704 个 segment**，共 **90,780 小时 / 7.66 TB**。

4. **比 zh/zh-cn 合计规模更大**: en-us 单语言即有 26.4M segment，接近 zh 和 zh-cn 合计的 27.9M；时长 90,780h 接近合计 115,101h 的 79%。

5. **Manifest (JSONL)**: 以 segment 为粒度，每条包含 `wav` 路径 + `start_time`/`end_time` 时间戳，可直接截取生成 utterance 级音频文件，对齐 Emilia 数据集格式。

6. **长音频切分**: 部分 episode 被切分为多段 (`_1`, `_2`, ...)，manifest 中按 split_idx 区分，同一 episode 的不同分段各自展开为独立 segment 条目。

7. **年份分布集中在 2025-2026**: 绝大多数 episode 来自 2025 年 (147,762) 和 2026 年 (37,375)，部分源元信息中缺少年份字段。
