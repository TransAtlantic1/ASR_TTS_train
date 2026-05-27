# Emilia 24k Validation

最小真实数据验证顺序：

1. `prepare_minimal_real_data.sh`
2. `run_smoke_train.sh`
3. `run_decode_export.sh`
4. `validate_outputs.py`

默认只验证 `egs/zipformer_24k_multilang/zipformer_24k_zh/ASR`，所有输入和产物都写到 `../experiments/main_flow_validation/emilia24k/`。

英文最小训练/验证循环使用独立隔离目录：

1. `prepare_minimal_real_data_en.sh`
2. `run_smoke_train_en.sh`

英文最小验证默认写到 `../experiments/main_flow_validation/emilia24k_en/`，只覆盖最小数据准备、训练循环和外部 dev 集验证循环，不覆盖 decode/export。
