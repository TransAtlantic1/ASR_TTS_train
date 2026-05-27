# Zipformer 24k EN CPU Cluster Runbook

标准主流程脚本：
- `run_data_pipeline.sh`
- `run_cluster_pipeline.sh`

已移除纯兼容 wrapper；host/worker 通过 `run_cluster_pipeline.sh --role ...` 启动。

当前 EN recipe 的主路径约定：
- 目标采样率：`24 kHz`
- 声学特征：F5-TTS 风格 `100` 维 log-mel
- train recordings 分片数：`1000`
- train feature shards：`1000`
- stage 7 总 worker 数：`9`
- 每机默认 `feature_num_workers=24`
- 部署拓扑：`1` 台 host + `8` 台子机
- host 会自动拉起本机 `worker 0`
- stage 7 worker 只依赖共享目录，不依赖机器间网络互通

## 1. 核心变化

- stage 3 不再做离线重采样，保留为兼容性空阶段。
- stage 4 直接消费原始 recordings manifests，并修正真实音频采样率、样本数和时长。
- stage 5 现在是兼容性 no-op；Emilia recipe-local `dev/test` 不再提特征。
- stage 7 在特征提取器内部在线重采样到 `24 kHz`。
- stage 7 启动门槛改为共享目录中的 `stage7.ready`；worker 可以提前启动，但不会在 host 完成 stage 0-6 之前开始处理 shard。
- host 既负责 stage `0-6`、stage 7 watcher/orchestrator、stage `8-10`，也会自动再起一个本机 worker 参与 stage 7。
- host/worker 对外使用同一个统一脚本，通过 `--role` 选择职责。
- 当前 `run_id` 上只允许一个活跃 host；第二个 host 会等待已有 host lease 释放或过期。
- 每个 `worker-index` 也有独立 lease；重复启动同 index worker 不会并发写同一份 stage7 状态或产物。
- host 不能帮远端子机拉起进程；每台子机必须本机自启动 worker。

## 2. 路径约定

推荐环境变量：

```bash
cd /inspire/hdd/project/embodied-multimodality/chenxie-25019/fj/ASR_TTS_train/egs/zipformer_24k_multilang/zipformer_24k_en/ASR
source /opt/conda/etc/profile.d/conda.sh
conda activate icefall
export PYTHONPATH=/inspire/hdd/project/embodied-multimodality/chenxie-25019/fj/ASR_TTS_train${PYTHONPATH:+:$PYTHONPATH}
export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python
export PUBLIC_ROOT=/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public
export DATASET_ROOT=/inspire/dataset/emilia/fc71e07
export ARTIFACT_ROOT=$PUBLIC_ROOT/emilia/fc71e07/icefall_emilia_en_24k
export LANGUAGE=en
```

主产物布局：
- 原始音频：`$DATASET_ROOT/EN`
- manifests / cuts / fbank / BPE：`$ARTIFACT_ROOT/data`
- 正式 EN 训练基路径：`$ARTIFACT_ROOT/exp/zipformer/emilia-en-24k-h200-md1000`
- 单次训练目录：`$ARTIFACT_ROOT/exp/zipformer/emilia-en-24k-h200-md1000/full.en.<RUN_STAMP>/run-<RUN_ID>`
- stage4_10 编排状态：`$ARTIFACT_ROOT/orchestration/stage4_10/en`
- 日志：`$ARTIFACT_ROOT/logs/stage4_10/<run_id>`

## 3. Stage 对照表

1. Stage 0：生成 Lhotse manifests
2. Stage 1：切分 train recordings 为 `1000` 片
3. Stage 2：可选的 MUSAN manifests
4. Stage 3：兼容性空阶段，不再离线重采样
5. Stage 4：文本规范化 + recordings 时长修正 + raw cuts
6. Stage 5：兼容性 no-op；外部 dev/eval cuts 不在 recipe 内部生成
7. Stage 6：切分 train raw cuts 为 `1000` 片
8. Stage 7：train 特征提取，`9` 个 worker 分布式处理
9. Stage 8：可选的 MUSAN 特征
10. Stage 9：合并 train split cut manifests
11. Stage 10：构建 `lang_bpe_en_500`

## 4. 数据集约定

- Emilia 全量都归入 `train`
- `run_data_pipeline.sh` 默认 `dev_ratio=0`、`test_ratio=0`
- 因此 recipe-local `dev/test` manifests 为空是当前主流程的正常结果
- 训练验证集必须通过外部 `--dev-cuts-path` 传入
- 当前正式 EN 全量训练入口 `run_train_full_en.sh` 默认使用外部 LibriSpeech `TEST_CLEAN` + `TEST_OTHER` cuts；若缺少合并后的 cuts，会在 `$ARTIFACT_ROOT/eval_assets/librispeech/LIBRISPEECH_TEST_CLEAN_OTHER_cuts.jsonl.gz` 自动生成
- 批量解码集合必须通过一个或多个 `--eval-cuts name=/path/to/cuts.jsonl.gz` 传入

外部 dev/eval manifest 格式固定为：

- 单个 Lhotse `CutSet` manifest 文件
- cuts 中已经带有预计算特征引用
- 文件本身可以来自 Librispeech、WenetSpeech 或别的测评集，只要满足上面这个 cuts 格式

对主流程日志的解释应保持一致：

- stage 0 仍然会生成 `dev/test` manifests 文件名，但在默认 `dev_ratio=0`、`test_ratio=0` 下它们为空
- stage 4 遇到空的 recipe-local `dev/test` split 时应视为“当前 recipe 不再内建 dev/test”的信息性现象
- 真正需要验证集时，不是在 recipe 内部打开 `dev/test_ratio`，而是准备外部 cuts 并通过训练/解码接口传入

## 5. 文本与标签规则

EN 当前固定规则：
- 做 `NFKC`
- 合并连续空白
- 保留原始大小写
- 保留原始标点

这条规则同时用于：
- stage 4 写入 `supervision.text`
- train/decode 送入 SentencePiece 的文本
- stage 10 的 BPE 训练文本

`raw_text` 仅保存在 supervision `custom` 字段里，不参与训练标签和建词表。

## 6. Stage 4 时长修正

stage 0 的实现现在推荐看 `local/build_emilia_lhotse_manifests.py`，它仍然直接继承 JSONL `duration` 构建初始 manifests，因此 stage 4 必须修正录音元数据并裁剪 supervision：

- 先对文本做规范化
- 再按 recordings 顺序对齐 normalized supervisions
- 如果 `supervision.end > recording.duration`，裁剪到录音末尾
- 如果 `supervision.start >= recording.duration`，直接丢弃该 supervision

这一步会输出：
- `*_recordings_*_audio_fixed.jsonl.gz`
- `*_supervisions_*_norm_fixed.jsonl.gz`
- `*_cuts_*_raw.jsonl.gz`

## 7. Host / Worker 协同

Host 脚本：

```bash
bash run_cluster_pipeline.sh \
  --role host \
  --supervise true \
  --language "$LANGUAGE" \
  --dataset-root "$DATASET_ROOT" \
  --artifact-root "$ARTIFACT_ROOT"
```

Host 行为：
- 初始化 `run_id`
- 获取当前 `run_id` 的 host lease
- 创建 `host-preparing.lock`
- 自动在本机后台拉起 `worker 0`
- 执行 stage `0-6`
- 成功后写出 `stage7.ready`
- 作为 watcher/orchestrator 负责 generation 分配、heartbeat 检查、失败重分配
- stage 7 完成后继续执行 stage `8-10`
- 如果 host 子进程异常退出，本机 supervisor 会自动重拉起并尝试续跑当前 `run_id`
- supervisor 退出时会回收自己拉起的 child 进程；共享 PID 文件只用于诊断，不承担排他语义

子机 worker 命令模板：

```bash
bash run_cluster_pipeline.sh \
  --role worker \
  --supervise true \
  --language "$LANGUAGE" \
  --dataset-root "$DATASET_ROOT" \
  --artifact-root "$ARTIFACT_ROOT" \
  --worker-index 4 \
  --num-stage7-workers 9
```

把 `--worker-index` 分别改成 `1..8`，每台子机运行一个。

Worker 等待顺序：
1. 读取共享目录中的 `current_run_id`
2. 获取自己 `worker-index` 对应的 worker lease
3. 等待 `stage7.ready`
4. 等待 `current_generation`
5. 读取 `worker-XX.shards.txt`
6. 处理分配到的 shard，并持续写 heartbeat

统一脚本的实际角色分工：

- `bash run_cluster_pipeline.sh --role host ...`：跑 `stage0-10`
- `bash run_cluster_pipeline.sh --role worker --worker-index N ...`：只跑 `stage7`

共享目录关键标记：
- `current_run_id`
- `host.lock/owner`
- `stage7/host-preparing.lock`
- `stage7/worker-locks/worker-XX.lock/owner`
- `stage7/stage7.ready`
- `stage7/current_generation`
- `stage7/generations/gen-XXXXX/worker-XX.shards.txt`
- `stage7/generations/gen-XXXXX/worker-XX.heartbeat`
- `stage7/generations/gen-XXXXX/worker-XX.done`
- `stage7/stage7.done`
- `pipeline.done`
- `pipeline.failed`

## 8. 特征存储与读取

- stage 7 每个 shard 的特征使用 `LilcomChunkyWriter` 写到 shard 自己的 `storage_path`
- 索引保存在同名 `.lca`
- 每个 `*_cuts_train.<idx>.jsonl.gz` 会记录对应的 `storage_path/storage_key`
- 训练和解码通过 cut manifest 懒加载预计算特征，不直接枚举特征目录

## 9. 失败恢复

- worker 失败或 heartbeat 超时后，host 会把当前 generation 视为失败，并基于剩余未完成 shard 新建下一代 generation。
- 已完成的 split cut manifest 和对应 `.lca` 特征索引会被复用，未完成 shard 会被重新分配。
- host 与子机都可以用 `--supervise true` 在本机自动重拉起子进程。
- stage7 stale/failed 只会触发重分配，不应再被日志标成 “completed” 或 “terminal success”。
- 如果 stage `0-6` 任一阶段失败，对应 `*.failed` marker 会被写入；worker 会检测到并退出，不会无限等待。
- host 只能重拉起本机 worker；远端 child 机器仍需要本机自己的 supervisor 负责重启。

## 10. 训练与解码示例

正式 EN 全量训练默认把外部 LibriSpeech `TEST_CLEAN` + `TEST_OTHER` 合并成一个 training-time validation cuts 文件，并传给 `--dev-cuts-path`。下面是 `8xH200` 的后台启动示例：

```bash
export PYTHONPATH=/inspire/hdd/project/embodied-multimodality/chenxie-25019/fj/ASR_TTS_train${PYTHONPATH:+:$PYTHONPATH}
export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python
export ARTIFACT_ROOT=/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public/emilia/fc71e07/icefall_emilia_en_24k
export CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7

export RUN_STAMP=$(date -u '+%Y%m%d_%H%M%S')
export RUN_ID=$(date -u '+%Y%m%d-%H%M%S')
export EXP_ROOT=$ARTIFACT_ROOT/exp/zipformer/emilia-en-24k-h200-md1000
export EXP_DIR=$EXP_ROOT/full.en.$RUN_STAMP/run-$RUN_ID
mkdir -p "$EXP_DIR"
export TRAIN_LOG=$EXP_DIR/nohup.train.log
export WANDB_MODE=offline
export WANDB_RUN_ID=$RUN_ID

nohup bash run_train_full_en.sh \
  --artifact-root "$ARTIFACT_ROOT" \
  --run-stamp "$RUN_STAMP" \
  --run-id "$RUN_ID" \
  --exp-root "$EXP_ROOT" \
  --exp-dir "$EXP_DIR" \
  >"$TRAIN_LOG" 2>&1 &

```

批量解码时传入一个或多个外部 eval cuts：

```bash
python3 zipformer/decode.py \
  --language "$LANGUAGE" \
  --artifact-root "$ARTIFACT_ROOT" \
  --eval-cuts dev-clean=/path/to/librispeech_dev_clean_cuts.jsonl.gz \
  --eval-cuts wenet=/path/to/wenetspeech_test_meeting_cuts.jsonl.gz
```

## 11. 验收检查

- `run_data_pipeline.sh --stage 3 --stop-stage 3` 只打印兼容性跳过日志，不再生成离线缓存。
- `run_data_pipeline.sh --stage 4 --stop-stage 4` 会生成 `audio_fixed`、`norm_fixed` 和 raw cuts。
- `run_data_pipeline.sh --stage 4 --stop-stage 4` 在默认全量归 `train` 配置下，若提示空 `dev/test` split，应视为符合预期，而不是失败信号。
- `run_data_pipeline.sh --stage 5 --stop-stage 5` 只打印外部 dev/eval 提示，不再尝试处理 recipe-local `dev/test`。
- `train_split_1000` 下应有 `1000` 个 raw cuts shards。
- stage 7 完成后应有 `1000` 个 `emilia_en_cuts_train.*.jsonl.gz` 和对应 `.lca`。
- `data/lang_bpe_en_500/` 下应产出：
  - `bpe.model`
  - `tokens.txt`
  - `L_disambig.pt`

## 12. 备注

- EN 原始采样率扫描显示大约 `87.8%` 音频本身就是 `24 kHz`，因此当前实现优先采用在线重采样而不是先构建离线缓存。
- recipe 当前没有 recipe-local `streaming_decode.py`；如果后续补充在线波形入口，也应继续保持 `raw source -> 24 kHz` 的单次重采样原则。
