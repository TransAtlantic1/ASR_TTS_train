# train_result

## 概览

本报告只覆盖当前 mainline/public 主训练产物，不包含 validation 线或 smoke run 产物。

当前 public 入口为：

- `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public/emilia/fc71e07/icefall_emilia_zh_24k`

其符号链接目标为：

- `/inspire/hdd/project/embodied-multimodality/public/emilia/fc71e07/icefall_emilia_zh_24k`

## 主训练产物位置

主训练 run 位于：

- `/inspire/hdd/project/embodied-multimodality/public/emilia/fc71e07/icefall_emilia_zh_24k/exp/zipformer/emilia-zh-24k-h200-md1000/full.zh.20260414_191852/run-20260414-191901`

已确认该 run 下存在：

- `epoch-1.pt` .. `epoch-10.pt`
- `checkpoint-80000.pt` .. `checkpoint-225000.pt`
- `best-train-loss.pt`
- `best-valid-loss.pt`
- `greedy_search/`
- `modified_beam_search/`

已确认评估汇总 CSV 位于：

- `/inspire/hdd/project/embodied-multimodality/public/emilia/fc71e07/icefall_emilia_zh_24k/eval_results/zh_public_current_avg1/summary/normalized_by_step.csv`

## checkpoint 说明

训练日志配置中记录了：

- `save_every_n=5000`
- `keep_last_k=30`

因此当前最早保留的 step checkpoint 是 `checkpoint-80000.pt`。`checkpoint-5000.pt` .. `checkpoint-75000.pt` 在更早训练过程中曾被保存，但随后因仅保留最近 30 个 step checkpoint 而被轮转清理。

训练日志中可以直接看到以下保存记录：

- `checkpoint-5000.pt`
- `checkpoint-75000.pt`
- `checkpoint-80000.pt`

## 训练 loss 图

下图直接基于已确认可读的训练日志绘制，实际使用的数据源为：

- `/inspire/hdd/project/embodied-multimodality/public/emilia/fc71e07/icefall_emilia_zh_24k/exp/zipformer/emilia-zh-24k-h200-md1000/full.zh.20260414_191852/run-20260414-191901/log/log-train-2026-04-14-19-19-17-0`

日志中提取了训练条目的 `Epoch`、`batch`、`loss`、`simple_loss`、`pruned_loss` 和 `tot_loss` 字段。另有本地 W&B 离线归档：

- `/inspire/hdd/project/embodied-multimodality/public/emilia/fc71e07/icefall_emilia_zh_24k/exp/zipformer/emilia-zh-24k-h200-md1000/full.zh.20260414_191852/wandb/wandb/offline-run-20260414_191917-gbs06fu5/run-gbs06fu5.wandb`

但本报告中的实际绘图序列来自上面的确认训练日志，而不是 W&B 离线归档。

![主训练 loss 曲线](results/pictures/train_loss_main.png)

## 结论

当前 public/mainline 主训练产物入口稳定指向旧 HDD 根，主 run 下已确认存在完整的 `epoch-1.pt` .. `epoch-10.pt`、保留窗口内的 `checkpoint-80000.pt` .. `checkpoint-225000.pt`、`best-train-loss.pt`、`best-valid-loss.pt` 以及 `greedy_search/`、`modified_beam_search/` 解码产物；后续评估汇总已落在 `eval_results/zh_public_current_avg1/summary/normalized_by_step.csv`。
