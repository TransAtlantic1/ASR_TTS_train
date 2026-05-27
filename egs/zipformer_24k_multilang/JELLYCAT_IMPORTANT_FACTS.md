# Jellycat Important Facts

Last updated: 2026-05-11 UTC.

## EN Data Layout

- Artifact root: `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public/jellycat/full/icefall_jellycat_en_24k`.
- Canonical clean data snapshot for this run: `data_clean_20260510T153150Z`.
- `data_clean_20260510T153150Z/lang_bpe_en_500` is complete for EN BPE training artifacts and contains regular files:
  - `transcript_words.txt`
  - `words.txt`
  - `unigram_500.model`
  - `unigram_500.vocab`
  - `bpe.model`
  - `tokens.txt`
- `data/lang_bpe_en_500` is also kept as regular files. Do not replace these BPE/lang files with symlinks to clean data.
- Training cuts are exposed through `data/fbank/en` as symlinks to `data_clean_20260510T153150Z/fbank/en`.
- For online feature extraction, EN has the required raw cuts:
  - top-level `jellycat_en_cuts_train_raw.jsonl.gz`
  - 1000 raw split manifests under `train_split_1000`
- For offline/precomputed-feature training, EN is not complete yet: 363/1000 `jellycat_en_cuts_train.####.jsonl.gz` split manifests were present when checked, and a local feature job was still writing later shards. Do not treat offline EN training as ready until this reaches 1000/1000.

## ZH Data Layout

- Artifact root: `/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public/jellycat/full/icefall_jellycat_zh_24k`.
- ZH online raw train split manifests exist under `data/fbank/zh/train_split_1000`.
- ZH top-level raw train cuts were generated for online-training symmetry at `data/fbank/zh/jellycat_zh_cuts_train_raw.jsonl.gz` using the temporary script `explore_plan/merge_zh_train_raw_top_level.sh`.
- The ZH data pipeline main flow was not changed; the top-level file is a post-hoc merged artifact from the 1000 raw split manifests.
- ZH `data/lang_hybrid_zh` is complete for current training. It contains `raw_text.txt`, `english_text.txt`, `char_tokens.txt`, `english_bpe.model`, `english_bpe.vocab`, `tokens.txt`, `words.txt`, `lang_type`, `lexicon.txt`, `lexicon_disambig.txt`, `L.pt`, and `L_disambig.pt`.
- ZH stage10 originally failed after saving `english_bpe.model` because `k2` loaded a broken system `libcuda.so.1`; it was fixed by putting `/usr/local/cuda-12.4/compat` first in `LD_LIBRARY_PATH` and rerunning only `prepare_lang_hybrid.py`.
- A local ZH stage7-10/feature process was still running when checked. Do not delete ZH partial files while that process is active.

## Training Requirements

- Current EN training with `run_train_full_en.sh --on-the-fly-feats true` needs `data/lang_bpe_en_500/bpe.model`, top-level train raw cuts, and validation cuts. It does not need `lexicon.txt`, `lexicon_disambig.txt`, `L.pt`, or `L_disambig.pt`.
- Current ZH training with `run_train_full_zh.sh --on-the-fly-feats true` expects top-level `data/fbank/zh/jellycat_zh_cuts_train_raw.jsonl.gz` at wrapper startup and uses the complete `data/lang_hybrid_zh`.
- Ordinary EN decoding paths such as greedy/beam/modified beam use `bpe.model`. LG/FST decoding would need additional lexicon/FST artifacts and is not covered by the current training command.
- The wrappers now accept raw train cuts in their startup checks when `--on-the-fly-feats true`.

## Environment Note

- If `import k2` fails with `libcuda.so.1: file too short`, put `/usr/local/cuda-12.4/compat` first in `LD_LIBRARY_PATH`, followed by the CUDA/NVIDIA libraries under `/opt/conda/envs/icefall/lib/python3.12/site-packages`.
- If ZH stage10 already produced `english_bpe.model`/`english_bpe.vocab` before this error, do not retrain BPE unless needed; rerun `zipformer_24k_zh/ASR/local/prepare_lang_hybrid.py --lang-dir <zh-lang-dir>` after fixing `LD_LIBRARY_PATH`.
- The HTML report command blocks include this `LD_LIBRARY_PATH` ordering.
