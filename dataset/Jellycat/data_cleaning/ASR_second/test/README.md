# H200 8-GPU ASR Benchmark

本目录用于在 H200 节点上测试 Qwen3-ASR 标注吞吐。因为本机不能访问 H200 的
`localhost:{port}`，所有会访问 ASR 服务的命令都必须在 H200 节点上执行。本机只通过
共享目录查看输出。

默认拓扑是 8 个独立服务副本：

```text
GPU 0 -> port 8000
GPU 1 -> port 8001
...
GPU 7 -> port 8007
```

对 Qwen3-ASR-1.7B 来说，这通常比一个 `TENSOR_PARALLEL_SIZE=8` 服务更适合吞吐测试。

## Files

```text
h200_preflight.sh             # H200 节点环境、模型、manifest、端口预检
h200_start_8gpu_services.sh   # 在 8 张 H200 上启动 8 个 qwen-asr-serve 副本
h200_stop_services.sh         # 停止某个 run_dir 记录的服务进程
h200_run_benchmark.sh         # 对 ZH/EN manifest 跑一次限量 benchmark
h200_benchmark_matrix.sh      # 跑多个 limit / 并发组合
h200_monitor_gpu.sh           # 周期性记录 nvidia-smi
summarize_benchmark.py        # 汇总 JSONL/timing 为 summary.md 和 summary.json
```

所有运行输出写入：

```text
data_cleaning/ASR_second/test/runs/<RUN_ID>/
```

该目录已被 `.gitignore` 排除。

## 1. On H200: Preflight

在 H200 节点上执行：

```bash
cd /inspire/hdd/project/embodied-multimodality/chenxie-25019/fj/ASR_TTS_train/dataset/Jellycat

bash data_cleaning/ASR_second/test/h200_preflight.sh
```

预检会确认：

- `meanaudio2` 可以运行；
- `qwen-asr-serve`、`qwen_asr`、`jiwer`、`pypinyin`、`opencc/zhconv` 可用；
- 模型目录存在；
- ZH/EN manifest 存在且可 dry-run；
- 端口 `8000-8007` 当前未被占用；
- 可见 GPU 数量和显存状态。

## 2. On H200: Start 8 Services

建议在 `tmux` 或 `screen` 里启动：

```bash
cd /inspire/hdd/project/embodied-multimodality/chenxie-25019/fj/ASR_TTS_train/dataset/Jellycat

RUN_ID=$(date -u '+%Y%m%d-%H%M%S')

RUN_ID="$RUN_ID" \
H200_GPUS=0,1,2,3,4,5,6,7 \
PORTS=8000,8001,8002,8003,8004,8005,8006,8007 \
GPU_MEMORY_UTILIZATION=0.85 \
MAX_MODEL_LEN=4096 \
bash data_cleaning/ASR_second/test/h200_start_8gpu_services.sh
```

脚本会写：

```text
data_cleaning/ASR_second/test/runs/<RUN_ID>/service_pids.tsv
data_cleaning/ASR_second/test/runs/<RUN_ID>/logs/gpu*_port*.log
data_cleaning/ASR_second/test/runs/<RUN_ID>/run_env.sh
```

启动脚本会等待每个端口 HTTP 可响应后退出。服务本身保持后台运行。

## 3. Optional: Monitor GPU

另开一个 H200 shell：

```bash
RUN_DIR=data_cleaning/ASR_second/test/runs/<RUN_ID> \
bash data_cleaning/ASR_second/test/h200_monitor_gpu.sh
```

输出：

```text
<RUN_DIR>/gpu_monitor.csv
```

## 4. On H200: First Benchmark

先跑小样本，确认端到端逻辑和吞吐：

```bash
RUN_DIR=data_cleaning/ASR_second/test/runs/<RUN_ID> \
LIMIT=100 \
WORKERS_PER_PORT=1 \
LABEL=limit100_wpp1 \
bash data_cleaning/ASR_second/test/h200_run_benchmark.sh
```

输出：

```text
<RUN_DIR>/benchmarks/limit100_wpp1_zh.jsonl
<RUN_DIR>/benchmarks/limit100_wpp1_zh.failed.jsonl
<RUN_DIR>/benchmarks/limit100_wpp1_zh.time.json
<RUN_DIR>/benchmarks/limit100_wpp1_en.jsonl
<RUN_DIR>/benchmarks/limit100_wpp1_en.failed.jsonl
<RUN_DIR>/benchmarks/limit100_wpp1_en.time.json
<RUN_DIR>/summary.md
<RUN_DIR>/summary.json
```

## 5. On H200: Concurrency Matrix

小样本成功后，再测并发：

```bash
RUN_DIR=data_cleaning/ASR_second/test/runs/<RUN_ID> \
LIMITS="100 1000" \
WORKERS_PER_PORT_LIST="1 2 4" \
bash data_cleaning/ASR_second/test/h200_benchmark_matrix.sh
```

停止加并发的信号：

- failed JSONL 中出现明显超时或连接错误；
- GPU 利用率长期达到 80%-95%；
- `audio_hours_per_wall_hour` 不再增长；
- 单次 benchmark wall time 增加但吞吐下降。

## 6. From Local Machine: Inspect Shared Results

本机不需要连 H200 端口。直接看共享目录：

```bash
RUN_DIR=/inspire/hdd/project/embodied-multimodality/chenxie-25019/fj/ASR_TTS_train/dataset/Jellycat/data_cleaning/ASR_second/test/runs/<RUN_ID>

cat "$RUN_DIR/summary.md"
tail -n 50 "$RUN_DIR/start.log"
tail -n 20 "$RUN_DIR/gpu_monitor.csv"
```

核心指标：

```text
utt_per_sec
audio_hours_per_wall_hour
failed
mean_wer
mean_cer
```

`audio_hours_per_wall_hour` 越高越好。比如 `120` 表示一小时 wall time 可处理约 120 小时音频。

## 7. Stop Services

在 H200 节点上执行：

```bash
RUN_DIR=data_cleaning/ASR_second/test/runs/<RUN_ID> \
bash data_cleaning/ASR_second/test/h200_stop_services.sh
```

如果服务进程没有按 PID 停掉，可最后再按端口人工排查：

```bash
ss -ltnp | grep -E ':800[0-7]\b'
```

## Notes

- 本测试默认只跑 limit，不做全量标注。
- 输出是 sidecar JSONL，不会修改原 manifest。
- 测试脚本会复用 `data_cleaning/ASR_second/verify_edit_data.py` 的 WER/CER 逻辑。
- 如果要测真正 full-run，请先用 `LIMIT=1000` 和 `LIMIT=10000` 找到稳定并发，再单独开正式输出目录。
