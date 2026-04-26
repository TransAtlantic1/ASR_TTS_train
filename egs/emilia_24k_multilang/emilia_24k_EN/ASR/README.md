# Emilia 24k ASR

这个目录是面向 Emilia 单语种 ASR 的 `24 kHz` recipe。

当前主链路的前端约定是：

- 目标采样率：`24 kHz`
- 声学特征：F5-TTS 风格 log-mel
- 输入维度：`100`
- 默认直接读取原始音频并在线重采样到 `24 kHz`

## 采样率原则

`emilia_24k` 统一遵循下面这个原则：

- 优先保持 `raw source -> 24 kHz` 的单次重采样
- 不推荐走 `raw source -> 16/32 kHz intermediate -> 24 kHz` 的级联重采样

默认主流程里，这个原则已经成立：

- `run_data_pipeline.sh` stage 3 保留为兼容性空阶段，不再生成离线重采样缓存
- `run_data_pipeline.sh` stage 4 直接基于原始 recordings manifests 生成 raw cuts，并修正真实音频时长
- `local/f5tts_mel_extractor.py` 会在特征提取时把非 `24 kHz` 音频在线重采样到 `24 kHz`
- 默认批量 `zipformer/decode.py` 消费的是预计算好的 `24 kHz` 特征

因此，常规训练和批量解码路径不会退化成多次重采样。

## 集群入口

EN CPU 集群当前推荐使用这三个名字：

- `run_cluster_pipeline.sh`
- `run_cluster_host_pipeline.sh`
- `run_cluster_worker_stage7.sh`

旧名字仍然保留为兼容转发：

- `run_cluster_prepare_host.sh`
- `run_cluster_stage7_worker.sh`
- `run_cluster_stage4_10.sh`

它们内部最终都转到同一个统一脚本：

- `run_cluster_pipeline.sh`

区别只有：

- `host` 角色负责 `stage 0-10`
- `worker` 角色只负责 `stage 7`

这也意味着：

- host 和 worker 的实际启动逻辑来自同一个脚本，只是参数不同
- 任意时刻只允许一个活跃 host 持有当前 `run_id` 的 host lease
- host 只能自动拉起本机 `worker 0`
- 每个 `worker-index` 任意时刻只允许一个活跃 owner；重复启动的同 index worker 会等待 lease 释放或过期
- host 不能替远端子机拉起或重启进程
- 每台子机都必须在本机自己运行 worker 命令

## 数据集约定

- Emilia 全量都视为 `train`
- recipe-local `dev/test` 已禁用
- 因此最小数据或全量主流程里看到空的 recipe-local `dev/test` manifests 是预期行为，不应视为失败
- `run_data_pipeline.sh` 的 stage 5 现在是兼容性 no-op
- 训练验证和批量解码必须通过外部 cuts manifest 传入

外部 dev/eval 集的固定格式：

- 单个 Lhotse `CutSet` manifest 文件路径，例如 `xxx_cuts_dev.jsonl.gz`
- cuts 内部必须已经带有预计算特征引用，能够被 `PrecomputedFeatures` 直接读取
- 训练用 `--dev-cuts-path /path/to/dev_cuts.jsonl.gz`
- 解码用可重复的 `--eval-cuts name=/path/to/cuts.jsonl.gz`

这也意味着：

- 如果 stage 4 日志提示 `dev/test` split 为空，应优先理解为“当前 recipe 不再内建 dev/test”，而不是“数据准备失败”
- 需要评测或训练验证时，应单独准备外部 dev/eval cuts，再通过训练或解码接口传入

## 特征存储与读取

- stage 5/7 的特征写入使用 `LilcomChunkyWriter`
- 每个 shard 的特征归档写到 `storage_path`，索引写到同名 `.lca`
- 对应的 cut manifest 会记录 `storage_path` 和 `storage_key`
- 训练和解码通过 cuts manifest 懒加载这些预计算特征，不直接扫描特征目录

## 注意点

- Emilia 原始音频常见为 `32 kHz`，不要把它理解成“先固定到某个中间采样率，再升到 24k”。
- 当前 EN CPU 集群流程使用 `1` 台 host + `8` 台子机；host 会自动再拉起本机 `worker 0`，因此 stage 7 总共有 `9` 个 worker。
- train recordings 分片数固定为 `1000`，train feature shards 固定为 `1000`。
- 每台机器默认 `feature_num_workers=24`，前提是本机共享内存和 CPU 资源足够。
- stage 7 worker 只通过共享目录协调；远端 worker 可以提前启动，但只有在 host 写出 `stage7.ready` 后才会开始处理 shard。
- host/worker 默认支持本机 supervisor 重启子进程，但恢复建立在 host lease 和 worker-index lease 上，而不是共享 PID 文件。
- worker 失败或 heartbeat 超时只会触发“保留已完成 shard、重分配剩余 shard”；stale generation 不应再被记成成功完成。
- 如果启用 MUSAN，本地 manifests 和 features 也会跟随 `artifact_root/data` 布局，不再依赖仓库当前目录下的 `data/`。
- 如果后续补充新的在线取波形入口，也应保持 `raw source -> 24 kHz` 的单次重采样原则。
- `zipformer/export.py` 里的示例现在只保留本 recipe 现有的批量 `decode.py` 路径；当前目录没有 recipe-local 的 `streaming_decode.py`。

更完整的执行命令和阶段说明见 [RUNBOOK.md](/inspire/hdd/project/embodied-multimodality/chenxie-25019/fj/icefall/egs/emilia_24k_multilang/emilia_24k_EN/ASR/RUNBOOK.md)。
