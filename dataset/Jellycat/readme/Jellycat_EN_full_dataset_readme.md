# Jellycat EN 全量数据集说明

## 数据概况

- 目标语言：`EN`
- 原始数据根目录：`/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/raw_data`
- 输出根目录：`/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat`
- Summary 文件数：`1`
- Manifest 组织方式：`单文件合并版`
## 长音频筛查与 VAD 切分规则

- `duration <= 30s`：保留原 utterance 和原 FLAC 路径。
- `30s < duration <= 60s`：对已经切好的 utterance FLAC 做 VAD，按自然语音段切分。
- `duration > 60s`：直接写入二次清理 reject 清单，不再进入 VAD。
- VAD child 如果仍然 `duration > 30s`，该 child 写入二次清理 reject 清单。
- VAD child 的 id 和文件名保留原始 `W` stem，并追加 `_V0001`、`_V0002` 等后缀。
- 二次清理产物先写入版本化 manifest/audio 输出；验证通过后再决定是否 promote 到正式入口。
- 该流程只处理 Jellycat 已切分后的 manifests 和音频目录，不修改 `raw_data`。

- 原始 shard 数：`16`
- 合并行数校验：`{'jellycat_EN_segments': 25066601, 'jellycat_EN_rejected': 1358103, 'jellycat_EN_recordings': 25066601, 'jellycat_EN_supervisions': 25066601}`

## 音频目录结构

```text
EN/EN_P000000/EN_P000000_S00000/flac/EN_P000000_S00000_W00000000.flac          # original utterance
EN/EN_P000000/EN_P000000_S00000/flac/EN_P000000_S00000_W00000000_V0001.flac    # optional VAD child from the same W
```

- `P`：podcast 数字编号。
- `S`：该 podcast 下按 episode-local speaker 映射后的数字编号。
- `W`：utterance 数字编号。
- VAD 拆分后的 child utterance 仍挂在原始 `W` 下，文件名和 id 增加 `_V0001`、`_V0002` 后缀，例如 `EN_P000000_S00000_W00000000_V0001.flac`。
- 原始哈希、原始 speaker、原始音频路径等信息保留在 segment manifest 元数据中。

## 统计摘要

- 接收 utterance 数：`25,066,601`
- 实际新切出的 FLAC 数：`25,066,601`
- 复用已存在 FLAC 数：`0`
- 接收总时长：86,406.45 小时（311,063,213.42 秒）
- 数字化 podcast 数：`3,511`
- 数字化 speaker key 数：`563,043`

## Rejected 统计

- 纯标签非语音（`non_speech_tag`）：`1,353,476`
- 非法时间标注（`invalid_time`）：`0`
- 切片失败（`cut_error`）：`4,627`

## 分语言统计

| 源语言 | 接收条数 | 接收时长 | 非语音 rejected | 非法时间 rejected | 切片失败 rejected |
|---|---:|---:|---:|---:|---:|
| en-us | 25,066,601 | 86,406.45 小时（311,063,213.42 秒） | 1,353,476 | 0 | 4,627 |

## Manifest 产物

以下是当前正式 manifest 入口。

### Segment manifests

- `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/EN/jellycat_EN_segments.jsonl.gz`

### Rejected manifests

- `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/EN/jellycat_EN_rejected.jsonl.gz`

### Lhotse recordings

- `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/EN/jellycat_EN_recordings.jsonl.gz`

### Lhotse supervisions

- `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/EN/jellycat_EN_supervisions.jsonl.gz`

### Podcast 级 manifests

- 根目录：`/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/EN`
- 文件模式：`EN/EN_P000000.jsonl`
- podcast manifest 数：`3,511`
- 总记录数：`25,066,601`
- 每个 `EN_Pxxxxx.jsonl` 与同名 podcast 音频目录并列，`wav` 字段相对语言根目录，结构仿照 Emilia 的 batch 级 jsonl。

### Podcast-level manifest summary

- `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/EN/jellycat_EN_segments.podcast_manifests.summary.json`

### Hard reject cleanup manifests

- 宽规则候选（`duration > 60s`）：
  `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/EN/jellycat_EN_reject_candidates.duration_gt_60s.jsonl`
- 当前选用 hard reject（`duration > 60s and chars_per_sec < 1.0`）：
  `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/EN/jellycat_EN_reject_candidates.duration_gt_60s.chars_per_sec_lt_1p0.jsonl`
- Summary：
  `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/EN/jellycat_EN_reject_candidates.summary.json`

- 宽规则候选数：`239`
- hard reject 数：`80`
- 扫描记录数：`25,066,601`
- 平均时长：`12.41` 秒；最大时长：`3,000.00` 秒。
- 平均字符数：`191.18`；平均 chars/sec：`14.78`。

当前 hard reject 清单用于 stage7 之后或其他后续步骤完成后再按 id 删除，避免中途改动已经开始处理的输入。

生成命令：

```bash
python dataset/Jellycat/prepare_data/generate_jellycat_reject_list.py --language EN --podcast-root /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/EN --output-dir /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/EN --duration-threshold 60 --chars-per-sec-threshold 1.0
```

删除命令示例，reject 文件通过参数传入：

```bash
python dataset/Jellycat/prepare_data/filter_jsonl_by_reject_list.py \
  --reject-jsonl /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/EN/jellycat_EN_reject_candidates.duration_gt_60s.chars_per_sec_lt_1p0.jsonl \
  --input /path/to/input.jsonl.gz \
  --output /path/to/output.filtered.jsonl.gz
```

## Shard 备份说明

- 原始分片 manifest 已合并为单文件 manifest。
- 原始 shard manifest 和 shard summary 已移动到同一 manifest 目录下的备份文件夹，避免下游误用重复入口。
- 当前训练和数据处理应优先使用上方单文件 manifest。

## 时长策略

manifest 和 Lhotse 中的时长统一来自目标 FLAC 头信息，即 `num_samples / sampling_rate`。
这与 Emilia 24k stage4 的 recording 时长修正策略保持一致。

## 复现命令

```bash
bash dataset/Jellycat/prepare_data/run_prepare_jellycat_en_shards.sh
python dataset/Jellycat/prepare_data/merge_jellycat_sharded_manifests.py
python dataset/Jellycat/prepare_data/write_jellycat_podcast_manifests.py --segment-manifest /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/EN/jellycat_EN_segments.jsonl.gz --output-root /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat --language EN --summary /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/EN/jellycat_EN_segments.summary.json --summary-output /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/EN/jellycat_EN_segments.podcast_manifests.summary.json
python dataset/Jellycat/prepare_data/write_jellycat_full_readme.py --summary /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/EN/jellycat_EN_segments.summary.json --output dataset/Jellycat/readme/Jellycat_EN_full_dataset_readme.md
```
