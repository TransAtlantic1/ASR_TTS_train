# Jellycat ZH 全量数据集说明

## 数据概况

- 目标语言：`ZH`
- 原始数据根目录：`/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/raw_data`
- 输出根目录：`/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat`
- Summary 文件数：`1`
- Manifest 组织方式：`单文件合并版`
- 原始 shard 数：`16`
- 合并行数校验：`{'jellycat_ZH_segments': 26697838, 'jellycat_ZH_rejected': 1234459, 'jellycat_ZH_recordings': 26697838, 'jellycat_ZH_supervisions': 26697838}`

## 音频目录结构

```text
ZH/ZH_P000000/ZH_P000000_S00000/flac/ZH_P000000_S00000_W00000000.flac          # original utterance
ZH/ZH_P000000/ZH_P000000_S00000/flac/ZH_P000000_S00000_W00000000_V0001.flac    # optional VAD child from the same W
```

- `P`：podcast 数字编号。
- `S`：该 podcast 下按 episode-local speaker 映射后的数字编号。
- `W`：utterance 数字编号。
- VAD 拆分后的 child utterance 仍挂在原始 `W` 下，文件名和 id 增加 `_V0001`、`_V0002` 后缀，例如 `ZH_P000000_S00000_W00000000_V0001.flac`。
- 原始哈希、原始 speaker、原始音频路径等信息保留在 segment manifest 元数据中。

## 统计摘要

- 接收 utterance 数：`26,697,838`
- 实际新切出的 FLAC 数：`25,473,832`
- 复用已存在 FLAC 数：`1,224,006`
- 接收总时长：111,230.13 小时（400,428,466.29 秒）
- 数字化 podcast 数：`8,995`
- 数字化 speaker key 数：`526,514`

## Rejected 统计

- 纯标签非语音（`non_speech_tag`）：`1,227,296`
- 非法时间标注（`invalid_time`）：`470`
- 切片失败（`cut_error`）：`6,692`

这里的 `jellycat_ZH_rejected.jsonl.gz` 是第一轮准备阶段 rejected manifest，只记录纯标签非语音、非法时间、切片失败等准备时剔除项。它不同于后续 hard reject 清洗清单。

## 分语言统计

| 源语言 | 接收条数 | 接收时长 | 非语音 rejected | 非法时间 rejected | 切片失败 rejected |
|---|---:|---:|---:|---:|---:|
| zh | 9,835,581 | 43,347.94 小时（156,052,598.51 秒） | 455,627 | 141 | 2,629 |
| zh-cn | 16,862,257 | 67,882.19 小时（244,375,867.78 秒） | 771,669 | 329 | 4,063 |

## Manifest 产物

以下是当前正式 manifest 入口。

### Segment manifests

- `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_segments.jsonl.gz`

### Rejected manifests

- `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_rejected.jsonl.gz`

### Lhotse recordings

- `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_recordings.jsonl.gz`

### Lhotse supervisions

- `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_supervisions.jsonl.gz`

### Hard reject cleanup manifests

- 宽规则候选（`duration > 60s`）：
  `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_reject_candidates.duration_gt_60s.jsonl`
- 当前选用 hard reject（`duration > 60s and chars_per_sec < 1.0`）：
  `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_reject_candidates.duration_gt_60s.chars_per_sec_lt_1p0.jsonl`
- Summary：
  `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_reject_candidates.summary.json`

当前 hard reject 清单用于 stage7 之后或其他后续步骤完成后再按 id 删除，避免中途改动已经开始处理的输入。

生成命令：

```bash
python dataset/Jellycat/prepare_data/generate_jellycat_reject_list.py \
  --duration-threshold 60 \
  --chars-per-sec-threshold 1.0
```

删除命令示例，reject 文件通过参数传入：

```bash
python dataset/Jellycat/prepare_data/filter_jsonl_by_reject_list.py \
  --reject-jsonl /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_reject_candidates.duration_gt_60s.chars_per_sec_lt_1p0.jsonl \
  --input /path/to/input.jsonl.gz \
  --output /path/to/output.filtered.jsonl.gz
```

## 长音频筛查与 VAD 切分规则

- `duration <= 30s`：保留原 utterance 和原 FLAC 路径。
- `30s < duration <= 60s`：对已经切好的 utterance FLAC 做 VAD，按自然语音段切分。
- `duration > 60s`：直接写入二次清理 reject 清单，不再进入 VAD。
- VAD child 如果仍然 `duration > 30s`，该 child 写入二次清理 reject 清单。
- VAD child 的 id 和文件名保留原始 `W` stem，并追加 `_V0001`、`_V0002` 等后缀。
- 二次清理产物先写入版本化 manifest/audio 输出；验证通过后再决定是否 promote 到正式入口。
- 该流程只处理 Jellycat 已切分后的 manifests 和音频目录，不修改 `raw_data`。

## Shard 备份说明

- 原始分片 manifest 已合并为单文件 manifest。
- 原始 shard manifest 和 shard summary 已移动到同一 manifest 目录下的备份文件夹，避免下游误用重复入口。
- 当前训练和数据处理应优先使用上方单文件 manifest。

## 时长策略

manifest 和 Lhotse 中的时长统一来自目标 FLAC 头信息，即 `num_samples / sampling_rate`。
这与 Emilia 24k stage4 的 recording 时长修正策略保持一致。

## 复现命令

```bash
bash dataset/Jellycat/prepare_data/run_prepare_jellycat_zh_shards.sh
python dataset/Jellycat/prepare_data/merge_jellycat_sharded_manifests.py
python dataset/Jellycat/prepare_data/write_jellycat_full_readme.py --summary /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_segments.summary.json --output dataset/Jellycat/readme/Jellycat_ZH_full_dataset_readme.md
```
