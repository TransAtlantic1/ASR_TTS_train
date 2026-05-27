# Jellycat 数据集说明

本目录保存 Jellycat 数据准备脚本和压缩后的数据集文档。历史 `readme/` 下的有价值 markdown 内容已经合并到本文档。

## 数据根目录

| 用途 | 路径 |
| --- | --- |
| 原始播客数据 | `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/raw_data` |
| utterance 级 Jellycat 数据 | `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat` |
| 清洗脚本和报告 | `/inspire/hdd/project/embodied-multimodality/chenxie-25019/fj/ASR_TTS_train/dataset/Jellycat/data_cleaning` |

当前清洗主线只纳入中文和英文。

语言 alias 归一化规则：

| 归一化语言 | Alias |
| --- | --- |
| `zh` | `ZH`, `zh`, `zh-cn`, `zh-CN`, `zh-ch`, `zh-hans`, `zh-tw`, `zh-yue`, `zh-yue-hk` |
| `en` | `EN`, `en`, `en-us`, `en-US` |

## 原始数据概况

原始 source manifest 是 raw data 根目录下的 segment 级 JSONL。

| 源语言 | Raw manifest | 有效 episode | 有效 segment | 有效时长 | 说明 |
| --- | --- | ---: | ---: | ---: | --- |
| `zh` | `manifest_zh.jsonl` | 100,206 | 10,293,979 | 44,810.6 h | 繁体中文，以台湾播客为主。 |
| `zh-cn` | `manifest_zh-cn.jsonl` | 172,444 | 17,638,318 | 70,290.5 h | 简体中文，下载覆盖不如 `zh` 和 `en-us` 完整。 |
| `en-us` | `manifest_en-us.jsonl` | 145,683 | 26,424,704 | 90,780.1 h | 美式英语，下载覆盖率较高。 |

历史 raw disk 估计：

| 源语言 | 播客数 | FLAC 文件数 | FLAC 大小 | 估计原始时长 |
| --- | ---: | ---: | ---: | ---: |
| `zh` | 3,580 | 116,049 | ~4.27 TB | ~48,872 h |
| `zh-cn` | 25,407 | 228,228 | ~7.04 TB | ~84,418 h |
| `en-us` | 3,529 | 185,936 | ~8.20 TB | ~90,780 h |

抽样检查显示音频为 24 kHz mono FLAC。长 episode 音频可能带 `_1`, `_2` 等切分后缀。

## Raw Manifest Schema

raw manifest 每行是一个可以从源 FLAC 截取的 segment。

| 字段 | 含义 |
| --- | --- |
| `id` | 源 segment id，通常为 `{lang}_{episode_hash[:12]}_{split_idx}_{seg_idx}`。 |
| `wav` | 相对源语言目录的源 FLAC 路径。 |
| `text` | 源转写文本。 |
| `start_time`, `end_time`, `duration` | 片段时间戳，单位秒。 |
| `language` | 源语言，例如 `zh`, `zh-cn`, `en-us`。 |
| `podcast_hash`, `episode_hash` | 源播客和 episode hash。 |
| `speaker` | 可选 episode-local speaker id，例如 `spk_0`。 |

raw transcript 中存在 `[Music]`, `[Silence]`, `[Noise]`, `[Human Sounds]`, `[Unintelligible Speech]` 等非语音标签。speaker id 是 episode 内局部编号，不同 episode 的 `spk_0` 不是同一个人。speaker id 缺失几乎完全由非语音标签 segment 造成。

## 已准备的 Jellycat 输出

当前正式 prepared manifests 位于：

```text
/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/{ZH,EN}
```

| Target | Source aliases | Segment manifest | Accepted utterances | Accepted hours | First-pass rejected | Podcast manifests |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| `ZH` | `zh`, `zh-cn` | `jellycat_ZH_segments.jsonl.gz` | 26,697,838 | 111,230.13 | 1,234,459 | 8,995 |
| `EN` | `en-us` | `jellycat_EN_segments.jsonl.gz` | 25,066,601 | 86,406.45 | 1,358,103 | 3,511 |

prepared utterance 音频使用数字化 podcast/speaker/utterance id：

```text
ZH/ZH_P000000/ZH_P000000_S00000/flac/ZH_P000000_S00000_W00000000.flac
EN/EN_P000000/EN_P000000_S00000/flac/EN_P000000_S00000_W00000000.flac
```

`P` 是数字化 podcast id，`S` 是该 podcast 下 episode-local speaker 的数字化 id，`W` 是 utterance id。源 hash 和源路径保留在 manifest metadata 中。

prepared segment 行至少包含：

| 字段 | 含义 |
| --- | --- |
| `id` | prepared Jellycat utterance id。 |
| `wav` | 相对 Jellycat output root 的 prepared 音频路径。 |
| `text` | reference transcript。 |
| `duration`, `sampling_rate`, `num_samples` | 音频时长和 FLAC metadata。 |
| `language` | target language，目前为 `ZH` 或 `EN`。 |
| `source_language` | 原始 source alias。 |
| `podcast`, `speaker` | prepared numeric ids。 |
| `source_manifest_id`, `source_wav`, `source_start_time`, `source_end_time` | 源数据追踪字段。 |
| `prefix_context`, `suffix_context`, `prefix_far`, `suffix_far` | 已补充的上下文字段。 |

prepared `duration` 来自写出的 FLAC header，即 `num_samples / sampling_rate`，与 Emilia 24k 中用真实音频帧修正 recording duration 的策略一致。

## Rejection 和 Policy 说明

first-pass rejected manifests 记录准备阶段剔除项：

| Target | `non_speech_tag` | `invalid_time` | `cut_error` |
| --- | ---: | ---: | ---: |
| `ZH` | 1,227,296 | 470 | 6,692 |
| `EN` | 1,353,476 | 0 | 4,627 |

second-pass policy reject sidecars 与正式 segment manifests 分离。当前记录的 hard reject 规则为：

```text
duration > 60s and chars_per_sec < 1.0
```

| Target | Broad `duration > 60s` | Strict hard reject |
| --- | ---: | ---: |
| `ZH` | 1,787 | 1,112 |
| `EN` | 239 | 80 |

当前 `jellycat_{ZH,EN}_segments.jsonl.gz` 路径仍名为 `segments`。只读全量 `zgrep` 检查已确认 ZH 和 EN 两个当前入口都没有 `duration >= 45s` 的记录，因此可视为已应用 45 秒 duration policy 的当前 ASR 输入。单独的 reject candidate JSONL 仍保留为历史/审计 sidecar。

## 长音频分析

历史分析报告统计如下；这些数字来自 policy sidecar 或旧分析产物，不代表当前 `segments` 入口仍保留这些长音频。

| Target | Records | Hours | Mean duration | `duration > 30s` records | `duration > 30s` hours | `duration > 60s` records |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `ZH` | 26,697,838 | 111,230.13 | 14.9985 s | 3,134,526 | 32,322.71 | 1,787 |
| `EN` | 25,066,601 | 86,406.45 | 12.4095 s | 3,308,082 | 33,392.64 | 239 |

旧 analysis 产物已经移动到 `analysis/manifest_policy_filter`，不放入 `data_cleaning`。其中统计脚本位于 `analysis/manifest_policy_filter/analyze_jellycat_language_stats.py`，duration/CPS 图位于 `analysis/manifest_policy_filter/figures/`。

## ASR 和 WER/CER 边界

ASR 阶段保持为 `data_cleaning/ASR_second`。

当前确认接口：

| 项目 | 值 |
| --- | --- |
| Runtime env | `meanaudio2` |
| Model path | Jellycat workspace 下的 `model/Qwen3-ASR-1.7B` |
| Service command | `qwen-asr-serve` |
| Endpoint | `http://localhost:{port}/v1/chat/completions` |
| Smoke output | `data_cleaning/ASR_second/smoke_outputs` |
| Full hyp output | `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/asr_hyp/qwen3_asr_1p7b` |

当前状态：

- `model/Qwen3-ASR-1.7B` 已通过现有 `huggingface-cli` 下载完成，并由 `.gitignore` 排除。
- `launch_qwen3_asr.sh` 已参数化，默认 `ASR_ENV=meanaudio2`，支持 `DRY_RUN=1`。
- `verify_edit_data.py` 已支持 `.jsonl/.jsonl.gz` manifest、`--audio_root`、`--dry-run`、`--limit`、`--ports`、`--workers-per-port`、`--timeout`、`--max-retries`、`--max-inflight`、sidecar `--output` 和 `--failed-output`，并按流式方式处理 manifest，避免全量加载所有记录和 future。
- 4090 smoke 已完成：实际使用 GPU 0、端口 8000、`GPU_MEMORY_UTILIZATION=0.85`、`TENSOR_PARALLEL_SIZE=1`、`MAX_MODEL_LEN=4096`。输出为 `data_cleaning/ASR_second/smoke_outputs/qwen3_asr_1p7b_smoke.jsonl`，6 条记录全部成功，`failed.jsonl` 为 0 条。
- smoke 指标：ZH 3 条平均 pinyin-tone3 WER `0.21523493118177503`、平均 CER `0.23206555349412492`；EN 3 条平均 WER `0.04062229904926534`。
- 依赖安装说明：按用户要求向 `meanaudio2` 安装了 `jiwer`、`pypinyin`、`opencc-python-reimplemented`、`zhconv`、`qwen-asr[vllm]`；其中 `qwen-asr[vllm]` 升级了 torch/transformers/vLLM 栈。

ASR sidecar JSONL 不得修改原 manifest。所选 manifest 中的 `wav` 是相对路径，ASR 工具应按以下规则解析：

```text
audio_abs_path = audio_root / record["wav"]
```

如果 `wav` 已经是绝对路径，则直接使用。

WER/CER 规则：

- 英文：lowercase + punctuation-normalized word WER。
- 中文：同时输出 pinyin + tone3 WER 和简繁归一化后的字符级 CER；中文主指标为 CER。
- scoring 时输出 edit diff。
- 阈值未明确前，不生成最终过滤候选。

## 已知数据问题

- `zh-cn` raw 下载完整度低于 `zh` 和 `en-us`。
- raw manifests 中存在纯非语音标签行；这些不会写入 speech manifest。
- 部分长 utterance 的 characters per second 极低，已记录在 second-pass reject sidecars。
- prepared segment manifests 很大：ZH gzip 约 11 GB，EN gzip 约 8.2 GB。
- 现有 logs 和 progress 文件可能包含运行历史，未单独确认前不要删除。

## 当前脚本布局

```text
data_cleaning/
  raw_to_utterance/
  manifest_policy_filter/
  ASR_second/
```

当前清洗阶段报告和复现说明见 `data_cleaning/report.md`。

## 复现命令

Sample checks：

```bash
bash dataset/Jellycat/data_cleaning/raw_to_utterance/tests/run_sample_prepare.sh
bash dataset/Jellycat/data_cleaning/raw_to_utterance/tests/run_sample_prepare_en.sh
```

全量 raw-to-utterance 入口：

```bash
bash dataset/Jellycat/data_cleaning/raw_to_utterance/run_prepare_jellycat_zh_shards.sh
bash dataset/Jellycat/data_cleaning/raw_to_utterance/run_prepare_jellycat_en_shards.sh
```

Policy sidecar 示例：

```bash
python dataset/Jellycat/data_cleaning/manifest_policy_filter/generate_jellycat_reject_list.py --language ZH
python dataset/Jellycat/data_cleaning/manifest_policy_filter/filter_jsonl_by_reject_list.py --reject-jsonl /path/to/reject.jsonl --input /path/to/input.jsonl.gz --output /path/to/output.filtered.jsonl.gz
python dataset/Jellycat/data_cleaning/manifest_policy_filter/add_jellycat_context_fields.py --help
python dataset/Jellycat/data_cleaning/manifest_policy_filter/apply_jellycat_duration45_reject_context.py --help
```
