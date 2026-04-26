# iter 自动解码结果汇总

本文件只覆盖当前 mainline/public 主训练 run 的 `test` 集自动解码结果。

## run 标识

- run id: `full.zh.20260414_191852/run-20260414-191901`
- greedy_search 目录：`/inspire/hdd/project/embodied-multimodality/public/emilia/fc71e07/icefall_emilia_zh_24k/exp/zipformer/emilia-zh-24k-h200-md1000/full.zh.20260414_191852/run-20260414-191901/greedy_search`
- modified_beam_search 目录：`/inspire/hdd/project/embodied-multimodality/public/emilia/fc71e07/icefall_emilia_zh_24k/exp/zipformer/emilia-zh-24k-h200-md1000/full.zh.20260414_191852/run-20260414-191901/modified_beam_search`

## 提取规则

- iter 范围：`iter-10000` 到 `iter-220000`，步长 `10000`
- greedy_search 文件模式：`wer-summary-test-iter-<iter>-avg-1-context-2-max-sym-per-frame-1.txt`
- modified_beam_search 文件模式：`wer-summary-test-iter-<iter>-avg-1-modified_beam_search-beam-size-4.txt`
- 每个文件都是两行 TSV；保留表头定义的 4 个实际指标列，取第 2 行数据行
- 列含义：`plain_CER`、`numeric_normalized_CER`、`plain_numeric_subset_CER`、`numeric_normalized_numeric_subset_CER`

## 汇总表

| iter | greedy_plain_CER | greedy_numeric_normalized_CER | greedy_plain_numeric_subset_CER | greedy_numeric_normalized_numeric_subset_CER | modified_plain_CER | modified_numeric_normalized_CER | modified_plain_numeric_subset_CER | modified_numeric_normalized_numeric_subset_CER |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10000 | 17.21 | 14.55 | 14.46 | 11.17 | 15.54 | 13.83 | 12.75 | 10.66 |
| 20000 | 15.23 | 12.02 | 16.19 | 12.44 | 13.23 | 11.34 | 13.98 | 11.82 |
| 30000 | 12.13 | 9.11 | 12.41 | 8.91 | 10.34 | 8.53 | 10.53 | 8.5 |
| 40000 | 12.66 | 9.57 | 13.33 | 9.73 | 10.74 | 8.88 | 11.24 | 9.11 |
| 50000 | 11.29 | 8.94 | 9.72 | 6.91 | 10.03 | 8.43 | 8.57 | 6.68 |
| 60000 | 11.0 | 8.71 | 9.43 | 6.67 | 9.92 | 8.31 | 8.31 | 6.39 |
| 70000 | 9.59 | 7.4 | 8.98 | 6.41 | 8.7 | 7.08 | 8.17 | 6.29 |
| 80000 | 9.09 | 6.9 | 8.57 | 6.02 | 8.24 | 6.62 | 7.74 | 5.87 |
| 90000 | 8.0 | 6.03 | 7.79 | 5.48 | 7.45 | 5.85 | 7.16 | 5.32 |
| 100000 | 8.01 | 5.94 | 7.71 | 5.32 | 7.25 | 5.66 | 6.99 | 5.14 |
| 110000 | 7.97 | 5.87 | 7.79 | 5.35 | 7.35 | 5.73 | 7.15 | 5.27 |
| 120000 | 7.94 | 5.83 | 7.73 | 5.29 | 7.19 | 5.63 | 6.97 | 5.16 |
| 130000 | 7.59 | 5.57 | 7.37 | 5.05 | 6.91 | 5.36 | 6.64 | 4.84 |
| 140000 | 7.69 | 5.89 | 7.27 | 5.18 | 7.22 | 5.71 | 6.82 | 5.06 |
| 150000 | 7.48 | 5.64 | 7.01 | 4.87 | 6.97 | 5.44 | 6.49 | 4.72 |
| 160000 | 7.4 | 5.6 | 7.06 | 4.95 | 6.92 | 5.42 | 6.58 | 4.83 |
| 170000 | 7.4 | 5.47 | 7.09 | 4.85 | 6.8 | 5.28 | 6.48 | 4.72 |
| 180000 | 7.17 | 5.25 | 6.87 | 4.66 | 6.62 | 5.11 | 6.36 | 4.59 |
| 190000 | 7.06 | 5.22 | 6.85 | 4.72 | 6.56 | 5.06 | 6.32 | 4.59 |
| 200000 | 7.06 | 5.13 | 6.81 | 4.56 | 6.55 | 5.03 | 6.27 | 4.5 |
| 210000 | 6.98 | 5.22 | 6.69 | 4.65 | 6.53 | 5.05 | 6.24 | 4.52 |
| 220000 | 7.04 | 5.21 | 6.62 | 4.52 | 6.51 | 5.03 | 6.14 | 4.43 |
