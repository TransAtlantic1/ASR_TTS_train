# Jellycat data_cleaning 功能报告

生成时间: 2026-05-27 UTC

本文档只覆盖两个目录:

- `Jellycat/data_cleaning/raw_to_utterance`
- `Jellycat/data_cleaning/manifest_policy_filter`

本文档是新增功能报告，不替代、不覆盖 `Jellycat/data_cleaning/report.md`。

## 1. 总体职责边界

当前重构后的职责边界是:

| 目录 | 主职责 | 不再承担的职责 |
| --- | --- | --- |
| `raw_to_utterance` | 从 `raw_data/manifest_*.jsonl` 和源音频中切出 24 kHz mono FLAC utterance，写 segment manifest、切分失败 rejected manifest、Lhotse recordings/supervisions，以及 podcast-level manifest。 | 不做内容策略过滤；不因为 `[Music]`、`[Lyric]`、括号标签、时长策略等训练清洗规则丢弃样本。 |
| `manifest_policy_filter` | 对已经切好的 segment/podcast/Lhotse cut 等 manifest 做策略过滤，生成 reject JSONL，合并 reject，过滤 podcast-level manifest、segment manifest 和训练用 Lhotse CutSet，并在过滤后重算 context。 | 不切音频；不从 raw_data 重新生成 utterance 音频。 |

这个边界很重要: `raw_to_utterance` 只保证音频和 manifest 结构可用；`manifest_policy_filter` 决定哪些样本不进入后续训练或标注。

## 2. 核心数据流

### 2.1 切分阶段: raw_to_utterance

输入:

- `--raw-root`, 默认 `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/raw_data`
- 源 manifest:
  - `raw_data/manifest_zh.jsonl`
  - `raw_data/manifest_zh-cn.jsonl`
  - `raw_data/manifest_en-us.jsonl`
- 源音频路径由每条 raw manifest 的 `wav` 字段和 source language 拼接得到。

输出:

- utterance FLAC:
  - `ZH/ZH_P000000/ZH_P000000_S00000/flac/ZH_P000000_S00000_W00000000.flac`
  - `EN/EN_P000000/EN_P000000_S00000/flac/EN_P000000_S00000_W00000000.flac`
- segment manifest:
  - `manifests/ZH/jellycat_ZH_segments.jsonl.gz`
  - `manifests/EN/jellycat_EN_segments.jsonl.gz`
- 切分失败 rejected manifest:
  - `jellycat_ZH_rejected*.jsonl.gz`
  - `jellycat_EN_rejected*.jsonl.gz`
- Lhotse manifest:
  - `jellycat_<LANG>_recordings*.jsonl.gz`
  - `jellycat_<LANG>_supervisions*.jsonl.gz`
- summary:
  - `jellycat_<LANG>_segments*.summary.json`
- podcast-level manifest:
  - `<LANG>/<LANG>_P000000.jsonl`

### 2.2 策略过滤阶段: manifest_policy_filter

输入通常是切分阶段或 ASR 数据准备阶段的产物:

- segment manifest: `jellycat_<LANG>_segments.jsonl.gz`
- podcast-level manifest: `<LANG>_P*.jsonl`
- reject JSONL: 由策略脚本产生或由多个来源合并
- 训练 cut: `jellycat_<lang>_cuts_train_raw.jsonl.gz` / `jellycat_<lang>_cuts_train.jsonl.gz`

输出:

- 待合并或最终合并的 reject JSONL
- reject summary JSON
- 过滤后的 podcast-level manifest，且重算 `prefix_context` / `suffix_context`
- 过滤后的 merged segment manifest
- 过滤后的 Lhotse CutSet JSONL.GZ

### 2.3 当前第一版 policy

第一版清洗口径来自 `jellycat_broad_non_speech_tag_scan.md`:

1. 丢弃 `duration < 0.5s` 的样本。
2. 丢弃 `duration > 45s` 的样本。
3. 在剩余样本中，丢弃 `text` 含任意括号片段的样本。

括号片段覆盖:

```text
[]  【】  ()  （）  <>  {}
```

脚本中具体类型:

| 类型 | 正则含义 |
| --- | --- |
| `square` | `[...]` |
| `full_square` | `【...】` |
| `paren` | `(...)` |
| `full_paren` | `（...）` |
| `angle` | `<...>` |
| `brace` | `{...}` |

每个括号片段最长 120 字符，且不跨行。

当前已生成的 pending reject 输出:

- `Jellycat/data_cleaning/manifest_policy_filter/outputs/pending_merge/jellycat_segments_policy_v1.pending_merge.reject.jsonl`
- `Jellycat/data_cleaning/manifest_policy_filter/outputs/pending_merge/jellycat_segments_policy_v1.pending_merge.summary.json`

摘要统计:

| 项 | 条数 | 小时 |
| --- | ---: | ---: |
| 输入总量 | 51,761,163 | 197,440.51h |
| 保留 | 51,157,435 | 196,155.08h |
| reject 总量 | 603,728 | 1,285.43h |
| `duration_lt_0.5s` | 80,125 | 10.07h |
| `duration_gt_45s` | 0 | 0.00h |
| `contains_bracket_span_v1` | 523,603 | 1,275.36h |

按语言:

| 语言 | `<0.5s` 条数/小时 | 括号条数/小时 | 总 reject 条数/小时 |
| --- | ---: | ---: | ---: |
| EN | 78,083 / 9.83h | 135,670 / 225.38h | 213,753 / 235.21h |
| ZH | 2,042 / 0.24h | 387,933 / 1,049.98h | 389,975 / 1,050.22h |

## 3. `raw_to_utterance` 目录功能

目录路径:

```text
Jellycat/data_cleaning/raw_to_utterance
```

### 3.1 当前推荐入口

| 场景 | 推荐入口 |
| --- | --- |
| 单进程 ZH sample 或小规模切分 | `run_prepare_jellycat_zh.sh` 或 `prepare_jellycat_zh.py` |
| 单进程 EN sample 或小规模切分 | `run_prepare_jellycat_en.sh` 或 `prepare_jellycat_en.py` |
| 全量 ZH 分片切分 | `run_prepare_jellycat_zh_shards.sh` |
| 全量 EN 分片切分 | `run_prepare_jellycat_en_shards.sh` |
| 分片结果合并 | `merge_jellycat_sharded_manifests.py` |
| 从 merged segment 写 podcast-level JSONL | `write_jellycat_podcast_manifests.py` |
| 查看切分进度 | `show_jellycat_progress.py` |

### 3.2 `prepare_jellycat.py`

核心切分脚本。EN/ZH 包装脚本最终都调用这里的 `main()`。

主要功能:

- 读取 `raw-root/manifest_<source_language>.jsonl`。
- 第一遍扫描构建稳定的 podcast/speaker 数字 ID 映射。
- 第二遍按 `start_time` / `duration` 从源音频中切出 FLAC。
- 写 segment manifest、切分失败 rejected manifest、Lhotse recordings/supervisions。
- 支持 hash shard: 通过 `crc32(entry_id) % num_shards == shard_index` 决定当前 shard 是否处理某条 raw entry。
- 支持复用已有 FLAC: 如果目标 FLAC 已存在且未指定 `--overwrite`，脚本会探测 sample rate、channels、frames、duration；不一致则尝试重切。

重要默认值:

| 配置 | 值 |
| --- | --- |
| sample rate | 24000 |
| audio format | FLAC, PCM_16 |
| 默认 target language | `ZH` |
| ZH 默认 source languages | `zh zh-cn` |
| EN 默认 source languages | `en-us` |
| 默认 output root | `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat` |

CLI 参数:

```text
--raw-root
--output-root
--target-language
--languages
--manifest-stem
--max-utterances-per-language
--max-lines-per-language
--num-shards
--shard-index
--overwrite
--skip-lhotse
--progress-path
--progress-interval-lines
```

输出路径规则:

- `manifest_dir = output_root / "manifests" / TARGET_LANGUAGE`
- `segment_manifest = manifest_dir / f"{manifest_stem}.jsonl.gz"`
- `rejected_manifest = manifest_dir / f"{manifest_stem.replace('segments', 'rejected')}.jsonl.gz"`
- `recordings = manifest_dir / f"{manifest_stem.replace('segments', 'recordings')}.jsonl.gz"`
- `supervisions = manifest_dir / f"{manifest_stem.replace('segments', 'supervisions')}.jsonl.gz"`

ID 和音频布局:

```text
<LANG>_P000000
<LANG>_P000000_S00000
<LANG>_P000000_S00000_W00000000
<LANG>/<LANG>_P000000/<LANG>_P000000_S00000/flac/<LANG>_P000000_S00000_W00000000.flac
```

segment record 主要字段:

| 字段 | 含义 |
| --- | --- |
| `id` | 目标 utterance id，例如 `ZH_P000001_S00002_W00000003` |
| `wav` | 相对 `output_root` 的 FLAC 路径 |
| `text` | raw manifest 文本，strip 后写入 |
| `duration` | 实际写出 FLAC 的时长，按 `num_samples / sampling_rate` 对齐 |
| `sampling_rate` | 24000 |
| `num_samples` | FLAC frame 数 |
| `language` | 目标语言 `ZH` 或 `EN` |
| `source_language` | 原 raw manifest 语言，如 `zh-cn`、`en-us` |
| `podcast` | 目标 podcast id |
| `speaker` | 目标 speaker id |
| `source_manifest_id` | raw manifest 原始 id |
| `source_podcast_hash` | raw `podcast_hash` |
| `source_episode_hash` | raw `episode_hash` |
| `source_speaker` | raw speaker 归一化结果 |
| `source_wav` | 源音频绝对/拼接路径 |
| `source_start_time` / `source_end_time` | 源音频切分时间边界 |
| `source_duration` | raw manifest duration |

Lhotse 输出:

- `RecordingSet`: 每条 segment 一个 recording，source 指向写出的 FLAC 绝对路径。
- `SupervisionSet`: `id == recording_id == segment id`，`start=0.0`，`duration` 对齐 FLAC，`custom` 中保留 source metadata。

`raw_to_utterance` 仍然会写 rejected manifest，但这些 reject 只表示“无法可靠切分”，不是内容清洗策略。当前原因包括:

| reason | 含义 |
| --- | --- |
| `empty_text` | 文本为空，无法形成训练样本 |
| `missing_wav` | raw entry 缺少 wav 字段 |
| `missing_source_wav` | 源音频文件不存在 |
| `invalid_time` | start/end/duration 非法 |
| `duration_mismatch` | `end_time - start_time` 与 `duration` 相差超过 0.05s |
| `missing_id` | raw entry 缺少 id |
| `missing_podcast_hash` | raw entry 缺少 podcast hash |
| `missing_episode_hash` | raw entry 缺少 episode hash |
| `cut_error:*` | soundfile 切音频失败 |
| `target_repair_error:*` | 已有目标 FLAC 探测失败后重切仍失败 |

注意:

- 当前版本不再包含旧的纯标签内容过滤函数；`[Music]` / `[Lyric]` / 括号片段等内容策略交给 `manifest_policy_filter`。
- `summary.json` 中的 `policy_filtering` 字段也说明了这一点。

常用命令:

```bash
python3 Jellycat/data_cleaning/raw_to_utterance/prepare_jellycat_zh.py \
  --raw-root /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/raw_data \
  --output-root /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat \
  --languages zh zh-cn \
  --manifest-stem jellycat_ZH_segments
```

```bash
python3 Jellycat/data_cleaning/raw_to_utterance/prepare_jellycat_en.py \
  --raw-root /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/raw_data \
  --output-root /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat \
  --languages en-us \
  --manifest-stem jellycat_EN_segments
```

### 3.3 `prepare_jellycat_zh.py`

ZH 包装入口。

内容很短:

- 从 `prepare_jellycat` import `main`。
- 调用 `main(default_target_language="ZH", default_languages=["zh", "zh-cn"])`。

作用:

- 固定默认目标语言为 ZH。
- 默认处理 `manifest_zh.jsonl` 和 `manifest_zh-cn.jsonl`。
- 其他 CLI 参数完全继承 `prepare_jellycat.py`。

### 3.4 `prepare_jellycat_en.py`

EN 包装入口。

内容很短:

- 从 `prepare_jellycat` import `main`。
- 调用 `main(default_target_language="EN", default_languages=["en-us"])`。

作用:

- 固定默认目标语言为 EN。
- 默认处理 `manifest_en-us.jsonl`。
- 其他 CLI 参数完全继承 `prepare_jellycat.py`。

### 3.5 `run_prepare_jellycat_zh.sh`

ZH 单进程 shell 入口。

默认环境变量:

| 环境变量 | 默认值 |
| --- | --- |
| `RAW_ROOT` | `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/raw_data` |
| `OUTPUT_ROOT` | `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat` |
| `NUM_SHARDS` | `1` |
| `SHARD_INDEX` | `0` |
| `MAX_UTTERANCES_PER_LANGUAGE` | `-1` |
| `MAX_LINES_PER_LANGUAGE` | `-1` |
| `PROGRESS_PATH` | `Jellycat/logs/full_prepare.progress.json` |
| `PROGRESS_INTERVAL_LINES` | `100000` |

实际调用:

```bash
python prepare_jellycat_zh.py \
  --languages zh zh-cn \
  --manifest-stem jellycat_ZH_segments \
  ...
```

适合:

- 小规模调试。
- 单 shard 运行。
- 手动追加参数，例如 `--overwrite`、`--max-lines-per-language`。

### 3.6 `run_prepare_jellycat_en.sh`

EN 单进程 shell 入口。

和 ZH 版本对称，差异是:

- 默认 progress path: `Jellycat/logs/full_prepare_en.progress.json`
- 调用 `prepare_jellycat_en.py`
- source language 固定为 `en-us`
- manifest stem 固定为 `jellycat_EN_segments`

### 3.7 `run_prepare_jellycat_zh_shards.sh`

ZH 全量分片切分入口。

主要功能:

1. 启动 `NUM_SHARDS` 个 shard，默认 16 个。
2. 控制并发 `MAX_PARALLEL`，默认 16。
3. 每个 shard 写独立日志、pid、status、exit_status、progress JSON。
4. 所有 shard 成功后自动运行:
   - `merge_jellycat_sharded_manifests.py`
   - `write_jellycat_podcast_manifests.py`
   - `write_jellycat_full_readme.py`
5. 最终写 `logs/full_prepare_sharded.status` 为 `done` 或 `failed`。

关键输出:

- `logs/full_prepare.shard00000-of-00016.log`
- `logs/full_prepare.shard00000-of-00016.progress.json`
- `manifests/ZH/jellycat_ZH_segments.shard00000-of-00016.jsonl.gz`
- 合并后 `manifests/ZH/jellycat_ZH_segments.jsonl.gz`
- podcast-level `ZH/ZH_P*.jsonl`

注意:

- 这是批处理入口，会写大量音频和 manifest。
- 后处理阶段会将 shard manifest 合并，并默认把 shard 文件移动到 backup 目录，除非合并脚本传 `--keep-shards`。

### 3.8 `run_prepare_jellycat_en_shards.sh`

EN 全量分片切分入口。

和 ZH 分片脚本对称，差异是:

- shard 日志前缀是 `full_prepare_en.*`。
- manifest root 是 `manifests/EN`。
- source language 是 `en-us`。
- 后处理会额外调用旧的 `generate_jellycat_reject_list.py`，生成 duration > 60s / low chars-per-sec 的 candidate reject 统计。
- 最终 README 可携带 reject summary。

注意:

- 这个脚本里的 reject list 是历史异常候选统计，不是当前第一版 `duration_0p5_45_contains_bracket_v1` policy。

### 3.9 `finalize_jellycat_en_outputs.sh`

EN 后处理补跑脚本。

作用:

- 等待 EN 分片任务全部成功。
- 如果 merged segment manifest 不存在，则运行 `merge_jellycat_sharded_manifests.py`。
- 重新写 EN podcast-level manifests。
- 重新写 EN README。
- 通过 `logs/finalize_jellycat_en_outputs.status` 记录状态。

适用场景:

- EN 分片切分已经完成，但自动后处理没有跑完或需要单独补跑。
- 不负责重新切音频。

### 3.10 `merge_jellycat_sharded_manifests.py`

分片 manifest 合并工具。

输入:

- `--manifest-dir`, 默认 ZH manifests 目录。
- `--stem`, 默认 `jellycat_ZH`。
- `--num-shards`, 默认 16。

它会合并四类文件:

```text
<stem>_segments.shard*.jsonl.gz
<stem>_rejected.shard*.jsonl.gz
<stem>_recordings.shard*.jsonl.gz
<stem>_supervisions.shard*.jsonl.gz
```

输出:

```text
<stem>_segments.jsonl.gz
<stem>_rejected.jsonl.gz
<stem>_recordings.jsonl.gz
<stem>_supervisions.jsonl.gz
<stem>_segments.summary.json
```

行为细节:

- 如果 merged output 已存在，直接报错，避免覆盖。
- 对每个 merged output 做行数校验。
- 合并 summary 中的 total/per-language stats。
- 默认把 shard manifest 和 shard summary 移动到 `sharded_manifest_backup_<timestamp>`。
- 传 `--keep-shards` 可保留 shard 文件。

### 3.11 `write_jellycat_podcast_manifests.py`

从 merged segment manifest 写 Emilia-style podcast-level JSONL。

输入:

- `--segment-manifest`: `jellycat_<LANG>_segments.jsonl.gz`
- `--output-root`: Jellycat 根目录
- `--language`: `ZH` 或 `EN`
- 可选 `--summary` 和 `--summary-output`

输出:

```text
<output-root>/<LANG>/<LANG>_P000000.jsonl
<output-root>/<LANG>/<LANG>_P000001.jsonl
...
```

行为细节:

- 写入每个 podcast 的临时文件 `<podcast>.jsonl.tmp`，结束后 rename 成 `<podcast>.jsonl`。
- `wav` 字段会去掉语言前缀，变成相对语言根目录的路径。
- 使用 `WriterCache` 限制同时打开的文件数量，默认 256。
- 默认如果已有 `<LANG>_P*.jsonl` 会报错；传 `--overwrite` 会先删除旧 podcast JSONL 和 tmp。
- 如果传 `--summary`，会把 podcast manifest 元信息写回 merged summary。

### 3.12 `show_jellycat_progress.py`

进度查看工具。

模式:

- 单文件模式: `--progress-path path/to/progress.json`
- 分片模式: `--progress-glob 'logs/full_prepare.*.progress.json'`
- watch 模式: `--watch`，每秒刷新一次。

显示信息:

- phase
- language
- percent/bar
- lines seen / expected
- accepted / rejected
- audio_written / audio_reused
- podcast/speaker counts

### 3.13 `tests/run_sample_prepare.sh`

ZH sample 运行脚本。

功能:

- 默认将 sample 输出到 `Jellycat/sample`。
- 先执行 `rm -rf "$SAMPLE_ROOT"`，再重新生成 sample。
- 调用 `prepare_jellycat_zh.py`，默认每个 source language 最多 8 条 accepted，最多读 2000 行。
- 运行 `validate_jellycat_sample.py`。

注意:

- 这个脚本会删除 `SAMPLE_ROOT`，只适合作为测试 sample 目录使用。
- 它不是全量数据入口。

### 3.14 `tests/run_sample_prepare_en.sh`

EN sample 运行脚本。

和 ZH sample 脚本对称:

- 默认输出到 `Jellycat/sample_en`。
- 先 `rm -rf "$SAMPLE_ROOT"`。
- 调用 `prepare_jellycat_en.py`。
- 运行 `validate_jellycat_en_sample.py`。

### 3.15 `tests/validate_jellycat_sample.py`

ZH sample 校验脚本。

输入:

```bash
python3 validate_jellycat_sample.py --sample-root Jellycat/sample
```

校验内容:

- 必须存在 segment/rejected/recordings/supervisions 四类 manifest。
- segment manifest 不为空。
- 每条 record 的 `language == ZH`。
- `wav` 路径符合 `ZH/ZH_Pxxxxxx/ZH_Pxxxxxx_Sxxxxx/flac/...flac`。
- FLAC 文件存在，sample rate 24000，mono。
- `num_samples`、`duration` 与音频真实信息一致。
- `podcast`、`speaker`、`id` 与路径一致。
- 保留 source metadata。
- Lhotse RecordingSet/SupervisionSet 数量与 segment record 数量一致。
- 写 `validation_summary.json`。

注意:

- 脚本仍保留了“纯方括号 tag 不应进入 speech manifest”和“rejected manifest 不为空”的历史断言。
- 当前职责边界下内容策略已经移到 `manifest_policy_filter`，因此如果 sample 中出现纯 tag 但可切分，这个旧断言可能需要随测试策略更新。

### 3.16 `tests/validate_jellycat_en_sample.py`

EN sample 校验脚本。

和 ZH 校验脚本对称，差异是:

- `language == EN`
- `wav` 路径正则以 `EN/EN_P...` 开头。
- recordings/supervisions 用 JSONL 直接读，而不是 Lhotse class。

同样保留了历史纯 tag 和 rejected 非空断言。

### 3.17 `legacy/prepare_jellycat_zh_legacy.py`

旧 ZH 切分脚本。

状态:

- legacy 版本，保留用于对照和追溯。
- 功能和当前 `prepare_jellycat.py + prepare_jellycat_zh.py` 很接近，但旧脚本内部固定 ZH 逻辑。
- 仍包含旧的 `is_non_speech_tag()` / pure square bracket 内容过滤逻辑。

不推荐作为新流程入口，因为当前重构要求内容策略过滤属于 `manifest_policy_filter`。

### 3.18 `legacy/prepare_jellycat_en_legacy.py`

旧 EN 切分脚本。

状态:

- legacy 版本，保留用于对照和追溯。
- 功能和当前 `prepare_jellycat.py + prepare_jellycat_en.py` 很接近，但旧脚本内部固定 EN 逻辑。
- 仍包含旧的 pure square bracket 内容过滤逻辑。

不推荐作为新流程入口。

### 3.19 `__pycache__` 文件

这些文件是 Python bytecode 缓存，不是源码入口:

```text
raw_to_utterance/__pycache__/merge_jellycat_sharded_manifests.cpython-311.pyc
raw_to_utterance/__pycache__/prepare_jellycat.cpython-311.pyc
raw_to_utterance/__pycache__/prepare_jellycat.cpython-312.pyc
raw_to_utterance/__pycache__/prepare_jellycat_en.cpython-311.pyc
raw_to_utterance/__pycache__/prepare_jellycat_en.cpython-312.pyc
raw_to_utterance/__pycache__/prepare_jellycat_zh.cpython-311.pyc
raw_to_utterance/__pycache__/prepare_jellycat_zh.cpython-312.pyc
raw_to_utterance/__pycache__/show_jellycat_progress.cpython-311.pyc
raw_to_utterance/__pycache__/write_jellycat_podcast_manifests.cpython-311.pyc
raw_to_utterance/legacy/__pycache__/prepare_jellycat_en_legacy.cpython-311.pyc
raw_to_utterance/legacy/__pycache__/prepare_jellycat_zh_legacy.cpython-311.pyc
raw_to_utterance/tests/__pycache__/validate_jellycat_en_sample.cpython-311.pyc
raw_to_utterance/tests/__pycache__/validate_jellycat_sample.cpython-311.pyc
```

它们可以由 Python 自动重新生成。报告中记录它们只是为了完整说明目录内文件。

## 4. `manifest_policy_filter` 目录功能

目录路径:

```text
Jellycat/data_cleaning/manifest_policy_filter
```

### 4.1 当前推荐入口

| 场景 | 推荐入口 |
| --- | --- |
| 从 segment manifest 生成当前第一版 policy reject | `build_jellycat_policy_rejects.py` |
| 合并多个 reject JSONL | `merge_reject_jsonl.py` |
| 合并 reject 后同步写 podcast-level manifest 和 segment manifest | `merge_reject_jsonl.py --podcast-root --output-podcast-root --segment-output` |
| 合并 reject 后过滤训练用 Lhotse cut | `merge_reject_jsonl.py --cut-input --cut-output` |
| 只给 manifest 或 ASR 标注输出补 context | `add_jellycat_context_fields.py` |
| 简单按 reject id 过滤 JSONL | `filter_jsonl_by_reject_list.py` |
| 查看第一版括号过滤策略依据 | `jellycat_broad_non_speech_tag_scan.md` |

### 4.2 `build_jellycat_policy_rejects.py`

当前第一版策略 reject 生成脚本。

主要功能:

- 只读扫描一个或多个 input manifest。
- 按顺序执行 policy:
  1. `duration < min_duration_sec`, 默认 0.5s。
  2. `duration > max_duration_sec`, 默认 45s。
  3. `text` 命中任意括号片段。
- 输出 standalone reject JSONL。
- 输出 summary JSON。
- 不修改输入 manifest。

CLI 参数:

```text
--inputs
--output
--summary-output
--policy-name
--min-duration-sec
--max-duration-sec
--id-field
--text-field
--duration-field
--language-field
--progress-interval
```

reject record 行为:

- 以原 record 为基础 `dict(record)`。
- 增加/覆盖:
  - `id`
  - `language`
  - `reject_policy`
  - `reason`
  - `duration_sec`
  - `source_manifest`
- 如果命中括号，额外写:
  - `matched_spans`
  - `matched_bracket_types`
  - `matched_bracket_details`

summary 内容:

- input/output 路径
- policy 名称
- seen/kept/rejected 条数
- 总小时数、保留小时数、reject 小时数
- 按 reason 的条数/小时
- 按语言的条数/小时
- 按输入文件的条数/小时
- bracket type 计数
- 前 20 个 examples

示例:

```bash
python3 Jellycat/data_cleaning/manifest_policy_filter/build_jellycat_policy_rejects.py \
  --inputs \
    /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/EN/jellycat_EN_segments.jsonl.gz \
    /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_segments.jsonl.gz \
  --output Jellycat/data_cleaning/manifest_policy_filter/outputs/pending_merge/jellycat_segments_policy_v1.pending_merge.reject.jsonl \
  --summary-output Jellycat/data_cleaning/manifest_policy_filter/outputs/pending_merge/jellycat_segments_policy_v1.pending_merge.summary.json
```

### 4.3 `merge_reject_jsonl.py`

reject 合并和同步过滤工具。

主要功能:

1. 合并多个 reject JSONL，按 `id` 去重。
2. 可选同步过滤 podcast-level manifests，并重算 context。
3. 可选写一个过滤后的 merged segment manifest。
4. 可选过滤一个或多个训练用 Lhotse CutSet JSONL.GZ。

CLI 参数:

```text
--inputs
--output
--id-field
--keep {first,last}
--language
--podcast-root
--output-podcast-root
--segment-output
--cut-input
--cut-output
--far-threshold-sec
--overwrite
```

合并逻辑:

- `--inputs` 可传多个 reject JSONL/JSONL.GZ。
- `--id-field` 默认 `id`。
- `--keep first` 时保留第一次出现的记录。
- `--keep last` 时后出现的记录覆盖前面的记录。
- 输出顺序保留第一次见到该 id 的顺序。

podcast-level 过滤逻辑:

- 需要同时传:
  - `--language`
  - `--podcast-root`
  - `--output-podcast-root`
- 扫描 `<language>_P*.jsonl`。
- 删除 id 在 reject ids 中的 record。
- 对保留 records 调用 `add_context()` 重算 context。
- 写到 `output_podcast_root / 原文件名`。

segment manifest 输出:

- 传 `--segment-output` 时，会把过滤后 podcast records 合并写出。
- 写出前调用 `add_language_prefix()`，确保 `wav` 和 context 中的 `wav` 带语言前缀，适配 merged segment manifest。

cut 过滤逻辑:

- `--cut-input` / `--cut-output` 必须成对出现，可重复传多组。
- 对每条 cut 收集以下 id:
  - `cut.id`
  - `recording.id`
  - `supervisions[].id`
  - `supervisions[].recording_id`
- 任一 id 命中 reject ids，则整条 cut 丢弃。

这个逻辑是必要的，因为实际 cut id 往往形如 `ZH_P..._W...-0`，而 reject id 通常是 supervision id `ZH_P..._W...`，所以不能只看 `cut.id`。

只合并 reject 示例:

```bash
python3 Jellycat/data_cleaning/manifest_policy_filter/merge_reject_jsonl.py \
  --inputs old.reject.jsonl new.reject.jsonl \
  --output merged.reject.jsonl
```

合并并同步中文 podcast/segment/cut 示例:

```bash
python3 Jellycat/data_cleaning/manifest_policy_filter/merge_reject_jsonl.py \
  --inputs jellycat_ZH_policy_v1.pending_merge.reject.jsonl \
  --output jellycat_ZH_policy_v1.merged.reject.jsonl \
  --language ZH \
  --podcast-root /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/ZH \
  --output-podcast-root /tmp/jellycat_ZH_podcast_filtered \
  --segment-output /tmp/jellycat_ZH_segments.filtered.jsonl.gz \
  --cut-input /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public/jellycat/full/icefall_jellycat_zh_24k/data/fbank/zh/jellycat_zh_cuts_train_raw.jsonl.gz \
  --cut-output /tmp/jellycat_zh_cuts_train_raw.filtered.jsonl.gz \
  --cut-input /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public/jellycat/full/icefall_jellycat_zh_24k/data/fbank/zh/jellycat_zh_cuts_train.jsonl.gz \
  --cut-output /tmp/jellycat_zh_cuts_train.filtered.jsonl.gz \
  --overwrite
```

### 4.4 `add_jellycat_context_fields.py`

context 字段生成和重算工具。

支持两种模式。

#### podcast mode

输入:

```text
--language
--podcast-root
--output-podcast-root
--segment-output 可选
```

行为:

- 读取 `<LANG>_P*.jsonl`。
- 每个 podcast 内部按 source episode 分组。
- 组内按时间排序，写 `prefix_context`、`suffix_context`、`prefix_far`、`suffix_far`。
- 可选写一个 merged segment JSONL/JSONL.GZ。

#### direct JSONL mode

输入:

```text
--language
--input-jsonl
--reject-jsonl 可选
--context-jsonl 可选
--output-jsonl
```

用法 1: 普通 source JSONL 重算 context

- `--input-jsonl` 本身包含 `source_wav` / `source_start_time` / `source_end_time`。
- `--reject-jsonl` 中的 id 会先被删除。
- 剩余 record 重算 context。

用法 2: ASR/人工标注输出补 context

- `--input-jsonl` 是 ASR 标注输出，可能只有 `id`、`hyp_text`、`wer`、`cer` 等字段，缺少 source timing。
- `--context-jsonl` 指向原始 segment manifest，提供 `source_wav`、`source_start_time`、`source_end_time`、`text` 等上下文排序字段。
- 脚本按 `id` 把 annotation 覆盖到 source record 上，但 source fields 优先保留。
- `hyp_text`、`wer`、`cer`、`ref_text`、`edit_distance` 等 annotation 字段不会被删除。

context 分组逻辑:

1. 优先按 `source_wav` 分组。
2. 没有 `source_wav` 时按 `source_episode_hash` 分组。
3. 再 fallback 到 `podcast`。

排序逻辑:

1. `source_start_time`, `source_end_time`
2. 如果缺失，使用 `start` + `duration`
3. 如果仍缺失 start，则从 `0.0` 开始，使用 `duration`

context object 字段:

| 字段 | 含义 |
| --- | --- |
| `id` | 邻居 utterance id |
| `wav` | 邻居 wav |
| `start_time` / `end_time` | 邻居在源 episode 中的时间边界 |
| `duration` | 邻居时长 |
| `speaker` | 邻居 speaker |
| `text` | 邻居文本 |
| `hyp_text` / `wer` / `cer` / `ref_text` / `edit_distance` | 如果邻居 record 中存在，则同步保留 |

`prefix_far` / `suffix_far`:

- 如果无邻居，为 `None`。
- 如果邻居存在，判断 gap 是否大于 `--far-threshold-sec`，默认 30s。

示例:

```bash
python3 Jellycat/data_cleaning/manifest_policy_filter/add_jellycat_context_fields.py \
  --language ZH \
  --input-jsonl asr_result.jsonl \
  --context-jsonl /path/to/jellycat_ZH_segments.jsonl.gz \
  --reject-jsonl merged.reject.jsonl \
  --output-jsonl asr_result.with_context.jsonl \
  --overwrite
```

### 4.5 `filter_jsonl_by_reject_list.py`

简单 JSONL 过滤工具。

输入:

```text
--reject-jsonl
--input
--output
--id-field
```

行为:

- 从 `reject-jsonl` 读取 `record["id"]`。
- 扫描 input JSONL/JSONL.GZ。
- 如果 `record[id_field]` 命中 reject ids，则丢弃。
- 输出保留 records。
- 打印 reject ids、kept、dropped、output。

限制:

- 只按一层 record id 过滤。
- 不重算 context。
- 不处理 Lhotse cut 的 nested supervision id。
- 对当前 Jellycat 主流程，通常优先使用 `merge_reject_jsonl.py`。

### 4.6 `generate_jellycat_reject_list.py`

历史异常候选 reject list 生成脚本。

主要用途:

- 扫描 podcast-level JSONL 或 merged segment manifest。
- 找出长时长样本和长时长且低字符速率样本。
- 生成 broad / strict 两类候选列表和 summary。

默认策略:

| 参数 | 默认值 |
| --- | --- |
| `--duration-threshold` | 60.0 |
| `--chars-per-sec-threshold` | 1.0 |
| `--workers` | 16 |
| `--chunk-size` | 128 |

输出文件名:

```text
<prefix>.duration_gt_60s.jsonl
<prefix>.duration_gt_60s.chars_per_sec_lt_1p0.jsonl
<prefix>.summary.json
```

candidate 字段:

- `id`
- `reason`
- `duration_sec`
- `text_len`
- `chars_per_sec`
- `podcast`
- `speaker`
- `wav`
- `text`
- source metadata

状态:

- 这是旧的异常候选统计工具。
- 不等价于当前第一版 `duration_0p5_45_contains_bracket_v1` policy。
- EN 分片脚本中仍会调用它生成历史 candidate summary。

### 4.7 `apply_jellycat_duration45_reject_context.py`

旧的 duration >= 45s 直接过滤与 context 重算脚本。

主要功能:

- 扫描 podcast-level JSONL。
- 将 `duration >= reject_threshold_sec` 的 record 作为 reject。
- 对保留 record 写 reject-aware context。
- 在 `--apply` 时替换 podcast JSONL 和 merged segment manifest。
- 可选 `--delete-audio` 删除被 reject 的 FLAC。
- 写 reject JSONL 和 summary。

CLI 参数:

```text
--language
--manifest
--podcast-root
--jellycat-root
--reject-root
--policy-name
--reject-threshold-sec
--far-threshold-sec
--apply
--delete-audio
--overwrite-backup
--max-podcast-files
--progress-interval
```

重要行为:

- 默认不传 `--apply` 时只统计，不替换 manifest。
- `--delete-audio` 必须和 `--apply` 一起使用。
- `--apply` 会 hardlink 备份原 manifest/podcast JSONL，然后用临时文件替换。

状态:

- 这是较早的 duration>=45s 专用脚本。
- 当前更推荐 `build_jellycat_policy_rejects.py` 生成 reject，再用 `merge_reject_jsonl.py` 同步 podcast/segment/cut。
- 如果继续使用此脚本，要明确它会在 `--apply` 时改原 podcast JSONL 和 segment manifest。

### 4.8 `write_jellycat_full_readme.py`

从切分 summary 和 reject summary 生成数据集 README 的工具。

输入:

```text
--summary
--summary-glob
--output
--reject-summary 可选
--include-vad-policy 可选
```

功能:

- 读取单个 summary 或多个 shard summary。
- 合并统计，包括总 records、时长、各语言 stats、路径块等。
- 可选读 reject summary，把 reject 候选信息写入 README。
- 可选写入尚未 promote 的 VAD 二次清理策略说明。

状态:

- 主要服务于 raw_to_utterance 全量切分后的 README 产出。
- 不执行过滤，也不修改 manifest。

### 4.9 `jellycat_broad_non_speech_tag_scan.md`

广义非语音标签扫描报告。

内容:

- 扫描当前 Jellycat `*_supervisions.jsonl.gz` 和旧 `*_rejected.jsonl.gz`。
- 比较现有 pure square tag、任意括号片段、keyword tag、pure broad tag 等口径。
- 统计 ZH/EN 剩余污染条数和小时数。
- 给出第一版清洗规划: 直接 hard reject 所有含括号片段的样本。
- 给出预期损失、输出物设计、实施步骤、验收标准和对照实验建议。

状态:

- 这是策略依据文档，不是可执行脚本。
- 当前 `build_jellycat_policy_rejects.py` 的括号规则与该报告的第一版规划保持一致。

### 4.10 `.gitignore`

当前内容:

```text
outputs/
__pycache__/
```

作用:

- 忽略 `manifest_policy_filter/outputs/` 下的大型生成产物。
- 忽略 Python bytecode 缓存。

### 4.11 `outputs/pending_merge/*`

当前 generated 输出:

```text
outputs/pending_merge/jellycat_segments_policy_v1.pending_merge.reject.jsonl
outputs/pending_merge/jellycat_segments_policy_v1.pending_merge.summary.json
```

说明:

- 这是当前第一版 policy 的待合并 reject 产物。
- `.reject.jsonl` 约 1.2GB，保留完整 reject record，便于人工检查和后续合并。
- `.summary.json` 约 49KB，记录统计摘要。
- 这些文件被 `.gitignore` 忽略，不应作为源码提交。

### 4.12 `__pycache__` 文件

这些文件是 Python bytecode 缓存，不是源码入口:

```text
manifest_policy_filter/__pycache__/add_jellycat_context_fields.cpython-311.pyc
manifest_policy_filter/__pycache__/add_jellycat_context_fields.cpython-312.pyc
manifest_policy_filter/__pycache__/apply_jellycat_duration45_reject_context.cpython-311.pyc
manifest_policy_filter/__pycache__/build_jellycat_policy_rejects.cpython-312.pyc
manifest_policy_filter/__pycache__/filter_jsonl_by_reject_list.cpython-311.pyc
manifest_policy_filter/__pycache__/filter_jsonl_by_reject_list.cpython-312.pyc
manifest_policy_filter/__pycache__/generate_jellycat_reject_list.cpython-311.pyc
manifest_policy_filter/__pycache__/generate_jellycat_reject_list.cpython-312.pyc
manifest_policy_filter/__pycache__/merge_reject_jsonl.cpython-312.pyc
manifest_policy_filter/__pycache__/write_jellycat_full_readme.cpython-311.pyc
```

## 5. 典型操作流程

### 5.1 从 raw_data 重新切分

ZH:

```bash
bash Jellycat/data_cleaning/raw_to_utterance/run_prepare_jellycat_zh_shards.sh
```

EN:

```bash
bash Jellycat/data_cleaning/raw_to_utterance/run_prepare_jellycat_en_shards.sh
```

### 5.2 生成第一版 pending reject

```bash
python3 Jellycat/data_cleaning/manifest_policy_filter/build_jellycat_policy_rejects.py \
  --inputs \
    /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/EN/jellycat_EN_segments.jsonl.gz \
    /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_segments.jsonl.gz \
  --output Jellycat/data_cleaning/manifest_policy_filter/outputs/pending_merge/jellycat_segments_policy_v1.pending_merge.reject.jsonl \
  --summary-output Jellycat/data_cleaning/manifest_policy_filter/outputs/pending_merge/jellycat_segments_policy_v1.pending_merge.summary.json
```

### 5.3 只合并中文并同步中文 manifest/cut

建议先写临时输出，再人工备份/替换原路径。不要在训练进程正在读取 cut 时替换。

```bash
python3 Jellycat/data_cleaning/manifest_policy_filter/merge_reject_jsonl.py \
  --inputs jellycat_ZH_policy_v1.pending_merge.reject.jsonl \
  --output jellycat_ZH_policy_v1.merged.reject.jsonl \
  --language ZH \
  --podcast-root /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/ZH \
  --output-podcast-root /tmp/jellycat_ZH_policy_v1_podcast \
  --segment-output /tmp/jellycat_ZH_segments.policy_v1.jsonl.gz \
  --cut-input /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public/jellycat/full/icefall_jellycat_zh_24k/data/fbank/zh/jellycat_zh_cuts_train_raw.jsonl.gz \
  --cut-output /tmp/jellycat_zh_cuts_train_raw.policy_v1.jsonl.gz \
  --cut-input /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public/jellycat/full/icefall_jellycat_zh_24k/data/fbank/zh/jellycat_zh_cuts_train.jsonl.gz \
  --cut-output /tmp/jellycat_zh_cuts_train.policy_v1.jsonl.gz \
  --overwrite
```

### 5.4 给 ASR 输出补 context

仅在 ASR/人工标注输出缺少 source timing、但后续需要上下文分析时使用。

```bash
python3 Jellycat/data_cleaning/manifest_policy_filter/add_jellycat_context_fields.py \
  --language ZH \
  --input-jsonl asr_output.jsonl \
  --context-jsonl /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_segments.jsonl.gz \
  --reject-jsonl jellycat_ZH_policy_v1.merged.reject.jsonl \
  --output-jsonl asr_output.with_context.jsonl \
  --overwrite
```

## 6. 和训练 cut 的关系

Jellycat ASR 训练通常不直接读取 `jellycat_<LANG>_segments.jsonl.gz`。训练读取的是 Lhotse CutSet:

- 在线特征训练 `--on-the-fly-feats true`:
  - `jellycat_<lang>_cuts_train_raw.jsonl.gz`
- 离线特征训练或默认 offline cut:
  - `jellycat_<lang>_cuts_train.jsonl.gz`
  - 或 `train_split_*` 下的分片 cut

因此，只过滤 segment/podcast manifest 不足以影响训练。要让 reject 真正从训练中消失，必须同步过滤训练实际读取的 cut。当前 `merge_reject_jsonl.py` 的 `--cut-input` / `--cut-output` 就是为这个用途增加的。

中文当前两个顶层训练 cut 都存在:

```text
/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public/jellycat/full/icefall_jellycat_zh_24k/data/fbank/zh/jellycat_zh_cuts_train_raw.jsonl.gz
/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public/jellycat/full/icefall_jellycat_zh_24k/data/fbank/zh/jellycat_zh_cuts_train.jsonl.gz
```

这两个都需要按 reject 同步过滤，否则在线/离线训练会看到不同的数据版本。

## 7. 原路径替换和 gzip 注意事项

`.jsonl.gz` 不能真正原地流式删除记录。删除中间 JSONL 行会改变后续 gzip 压缩流，正确做法只能是:

1. 读原文件。
2. 流式写新的临时 gzip。
3. 校验临时文件。
4. 把原文件改名成 backup。
5. 把临时文件 rename 到原路径。

这叫“原路径替换”，不叫真正的原地修改。

对训练 cut 尤其要注意:

- 不要在训练进程正在读取时替换。
- 英文 public 顶层 raw cut 是 symlink，替换时要先确认是替换 symlink 还是 symlink target。
- 中文 top-level raw/offline cut 是普通文件，替换逻辑更直接，但仍要先备份。

## 8. 已知注意点

1. `raw_to_utterance/tests/*validate*` 中仍保留旧的 pure-tag 断言，与“内容策略过滤移出 raw_to_utterance”的新边界不完全一致。后续如果要把 sample test 作为回归测试，应更新这些断言。
2. `generate_jellycat_reject_list.py` 和 `apply_jellycat_duration45_reject_context.py` 是历史策略工具，不应和当前第一版 bracket policy 混淆。
3. `merge_reject_jsonl.py` 写 podcast/segment 时会一次读取单个 podcast JSONL 到内存；这是按 podcast 粒度工作，风险低于全量载入。
4. `add_jellycat_context_fields.py` direct JSONL + `--context-jsonl` 会载入 annotation id map。大规模 ASR 输出使用时要确认内存足够。
5. `manifest_policy_filter/outputs/` 和 `__pycache__/` 是 generated/cache 内容，已被 `.gitignore` 忽略。

## 9. 文件清单覆盖确认

### `manifest_policy_filter` 源文件与文档

```text
.gitignore
add_jellycat_context_fields.py
apply_jellycat_duration45_reject_context.py
build_jellycat_policy_rejects.py
filter_jsonl_by_reject_list.py
generate_jellycat_reject_list.py
jellycat_broad_non_speech_tag_scan.md
merge_reject_jsonl.py
write_jellycat_full_readme.py
```

### `manifest_policy_filter` generated/cache

```text
__pycache__/*.pyc
outputs/pending_merge/jellycat_segments_policy_v1.pending_merge.reject.jsonl
outputs/pending_merge/jellycat_segments_policy_v1.pending_merge.summary.json
```

### `raw_to_utterance` 源文件

```text
finalize_jellycat_en_outputs.sh
merge_jellycat_sharded_manifests.py
prepare_jellycat.py
prepare_jellycat_en.py
prepare_jellycat_zh.py
run_prepare_jellycat_en.sh
run_prepare_jellycat_en_shards.sh
run_prepare_jellycat_zh.sh
run_prepare_jellycat_zh_shards.sh
show_jellycat_progress.py
write_jellycat_podcast_manifests.py
```

### `raw_to_utterance` tests

```text
tests/run_sample_prepare.sh
tests/run_sample_prepare_en.sh
tests/validate_jellycat_en_sample.py
tests/validate_jellycat_sample.py
```

### `raw_to_utterance` legacy/cache

```text
legacy/prepare_jellycat_en_legacy.py
legacy/prepare_jellycat_zh_legacy.py
__pycache__/*.pyc
legacy/__pycache__/*.pyc
tests/__pycache__/*.pyc
```

