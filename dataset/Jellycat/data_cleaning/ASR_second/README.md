# ASR_second

This stage keeps the existing directory and script names. It covers Qwen3-ASR service launch, sidecar hyp generation, and WER/CER verification. Full H200 annotation was not run.

Current scripts:

```text
launch_qwen3_asr.sh
example_qwen3_asr_vllm.py
verify_edit_data.py
```

## Current Status

| Item | Status |
| --- | --- |
| Model | Downloaded to `MODEL_PATH` with existing `huggingface-cli`. |
| Launcher | `launch_qwen3_asr.sh` is parameterized and supports `DRY_RUN=1`. |
| Verification script | `verify_edit_data.py` supports legacy `metafile.jsonl` and Jellycat `.jsonl/.jsonl.gz` manifests. |
| 4090 smoke | Completed on 2026-05-15: 6 records succeeded, 0 failed. |
| Full H200 run | Template only; not executed. |

Installed dependency status in `meanaudio2` after the explicit user request:

| Check | Result |
| --- | --- |
| `qwen-asr-serve` | available |
| `qwen_asr` | available |
| `jiwer` | available |
| `pypinyin` | available |
| `opencc` and `zhconv` | available |
| `requests` | available |
| `tqdm` | available |
| `vllm` | available |

Installing `qwen-asr[vllm]` upgraded key packages in `meanaudio2`, including `torch==2.9.1+cu128`, `transformers==4.57.6`, and `vllm==0.14.0`.

Actual 4090 smoke launch:

| Resource | Result |
| --- | --- |
| GPU | `CUDA_VISIBLE_DEVICES=0` |
| Port | `PORTS=8000` |
| Memory setting | `GPU_MEMORY_UTILIZATION=0.85` |
| Tensor parallel | `TENSOR_PARALLEL_SIZE=1` |
| Max model length | `MAX_MODEL_LEN=4096` |
| Service cleanup | stopped after smoke; port 8000 was free afterward |

## Confirmed Paths

```text
MODEL_PATH=/inspire/hdd/project/embodied-multimodality/chenxie-25019/fj/ASR_TTS_train/dataset/Jellycat/model/Qwen3-ASR-1.7B
ASR_INPUT_MANIFEST_ZH=/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_segments.jsonl.gz
ASR_INPUT_MANIFEST_EN=/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/EN/jellycat_EN_segments.jsonl.gz
AUDIO_ROOT=/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat
SMOKE_OUTPUT_DIR=/inspire/hdd/project/embodied-multimodality/chenxie-25019/fj/ASR_TTS_train/dataset/Jellycat/data_cleaning/ASR_second/smoke_outputs
HYP_OUTPUT_ROOT=/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/asr_hyp/qwen3_asr_1p7b
FAILED_OUTPUT_PATH=/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/asr_hyp/qwen3_asr_1p7b/failed.jsonl
```

Manifest fields:

```text
ID_FIELD=id
AUDIO_FIELD=wav
REF_TEXT_FIELD=text
LANG_FIELD=language
DURATION_FIELD=duration
```

`wav` is relative in sampled ZH/EN manifests. `verify_edit_data.py` supports `--audio_root`; if `wav` is absolute, it uses that path directly.

## Service Interface

Use `qwen-asr-serve`, not a Python API main flow.

```text
http://localhost:{port}/v1/chat/completions
```

`launch_qwen3_asr.sh` accepts these environment variables:

```text
MODEL_PATH
ASR_ENV=meanaudio2
CUDA_VISIBLE_DEVICES
PORTS
LOG_DIR
GPU_MEMORY_UTILIZATION
TENSOR_PARALLEL_SIZE
HOST
DRY_RUN
MAX_MODEL_LEN
VLLM_EXTRA_ARGS
```

Dry-run example:

```bash
DRY_RUN=1 CUDA_VISIBLE_DEVICES=0 PORTS=8000 ASR_ENV=meanaudio2 MAX_MODEL_LEN=4096 \
  bash data_cleaning/ASR_second/launch_qwen3_asr.sh
```

## Smoke Test Result

The real smoke was run with three ZH samples and three EN samples.

```text
CUDA_VISIBLE_DEVICES=0
PORTS=8000
SMOKE_SAMPLES_PER_LANG=3
GPU_MEMORY_UTILIZATION=0.85
TENSOR_PARALLEL_SIZE=1
MAX_MODEL_LEN=4096
```

Output files:

```text
data_cleaning/ASR_second/smoke_outputs/qwen3_asr_1p7b_smoke.jsonl
data_cleaning/ASR_second/smoke_outputs/failed.jsonl
```

Smoke summary:

| Language | Records | Failures | Mean WER | Mean CER |
| --- | ---: | ---: | ---: | ---: |
| ZH | 3 | 0 | 0.21523493118177503 pinyin-tone3 WER | 0.23206555349412492 |
| EN | 3 | 0 | 0.04062229904926534 | n/a |

The smoke output sidecar has 6 rows. The failed output has 0 rows.

Commands used for the smoke:

```bash
ASR_ENV=meanaudio2 \
CUDA_VISIBLE_DEVICES=0 \
PORTS=8000 \
GPU_MEMORY_UTILIZATION=0.85 \
TENSOR_PARALLEL_SIZE=1 \
MAX_MODEL_LEN=4096 \
LOG_DIR=/inspire/hdd/project/embodied-multimodality/chenxie-25019/fj/ASR_TTS_train/dataset/Jellycat/data_cleaning/ASR_second/logs \
  bash data_cleaning/ASR_second/launch_qwen3_asr.sh

conda run -n meanaudio2 python data_cleaning/ASR_second/verify_edit_data.py \
  --manifest /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_segments.jsonl.gz \
  --limit 3 \
  --audio_root /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat \
  --ports 8000 \
  --workers-per-port 1 \
  --timeout 600 \
  --max-retries 1 \
  --max-inflight 2 \
  --output data_cleaning/ASR_second/smoke_outputs/qwen3_asr_1p7b_smoke.jsonl \
  --failed-output data_cleaning/ASR_second/smoke_outputs/failed.jsonl

conda run -n meanaudio2 python data_cleaning/ASR_second/verify_edit_data.py \
  --manifest /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/EN/jellycat_EN_segments.jsonl.gz \
  --limit 3 \
  --audio_root /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat \
  --ports 8000 \
  --workers-per-port 1 \
  --timeout 600 \
  --max-retries 1 \
  --max-inflight 2 \
  --output data_cleaning/ASR_second/smoke_outputs/qwen3_asr_1p7b_smoke.jsonl \
  --failed-output data_cleaning/ASR_second/smoke_outputs/failed.jsonl
```

The first Prompt 3 pass only completed dry-run/preflight and was blocked by missing dependencies; that status has been corrected here. Full H200 annotation is still not run.

## H200 Command Template

Command template only; do not execute full annotation from this pass.

For H200 machines that cannot accept connections from this local machine, use the shared-directory
benchmark kit under:

```text
data_cleaning/ASR_second/test/
```

That workflow starts services and runs benchmark clients on the H200 node, then writes logs,
JSONL outputs, timing files, and summaries into `data_cleaning/ASR_second/test/runs/<RUN_ID>/`
for local inspection through the shared filesystem.

```bash
conda activate meanaudio2
export CUDA_VISIBLE_DEVICES=<H200_GPU_ID>

MODEL_PATH=/inspire/hdd/project/embodied-multimodality/chenxie-25019/fj/ASR_TTS_train/dataset/Jellycat/model/Qwen3-ASR-1.7B
PORT=8000
GPU_MEMORY_UTILIZATION=0.85
TENSOR_PARALLEL_SIZE=1
RUN_ID=$(date -u '+%Y%m%d-%H%M%S')
LOG_DIR=/inspire/hdd/project/embodied-multimodality/chenxie-25019/fj/ASR_TTS_train/dataset/Jellycat/data_cleaning/ASR_second/logs/h200_${RUN_ID}

mkdir -p "$LOG_DIR"

qwen-asr-serve "$MODEL_PATH" \
  --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --tensor-parallel-size "$TENSOR_PARALLEL_SIZE" \
  > "$LOG_DIR/h200_port${PORT}.log" 2>&1 &

echo "pid=$!"
```

## Full-Run Hyp Template

Template only; do not execute from this pass. This writes sidecar JSONL and does not overwrite source manifests.

```bash
HYP_OUTPUT_ROOT=/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/asr_hyp/qwen3_asr_1p7b
FAILED_OUTPUT_PATH=/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/asr_hyp/qwen3_asr_1p7b/failed.jsonl
AUDIO_ROOT=/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat

python data_cleaning/ASR_second/verify_edit_data.py \
  --manifest /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/ZH/jellycat_ZH_segments.jsonl.gz \
  --manifest /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/EN/jellycat_EN_segments.jsonl.gz \
  --audio_root "$AUDIO_ROOT" \
  --ports 8000 \
  --workers-per-port 1 \
  --timeout 300 \
  --max-retries 3 \
  --max-inflight 8 \
  --output "$HYP_OUTPUT_ROOT/qwen3_asr_1p7b.sidecar.jsonl" \
  --failed-output "$FAILED_OUTPUT_PATH"
```

## Sidecar Output

Do not write hyp text back to the original manifest.

Sidecar JSONL fields should include at least:

```text
id
audio_path
wav
language
ref_text
hyp_text
raw_asr_output
wer
cer
edits
error
```

## Normalization And Metrics

Language alias normalization:

| Normalized | Aliases |
| --- | --- |
| `zh` | `ZH`, `zh`, `zh-cn`, `zh-CN`, `zh-ch`, `zh-hans`, `zh-tw`, `zh-yue`, `zh-yue-hk` |
| `en` | `EN`, `en`, `en-us`, `en-US` |

English metric:

- lowercase;
- punctuation-normalized;
- word WER.

Chinese metrics:

- pinyin + tone3 WER;
- character CER as the main metric;
- simplified/traditional normalization is required before CER.

Use `opencc` or `zhconv` for simplified/traditional normalization. Both are now available in `meanaudio2`.
