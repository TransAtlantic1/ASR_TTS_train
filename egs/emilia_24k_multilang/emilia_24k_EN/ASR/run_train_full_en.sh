#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ICEFALL_ROOT=$(cd -- "${SCRIPT_DIR}/../../../.." && pwd)
PARSE_OPTIONS_SH="${ICEFALL_ROOT}/icefall/shared/parse_options.sh"

public_root=/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public
dataset_root=/inspire/dataset/emilia/fc71e07
bench_root="${public_root}/eval"
artifact_root=""

test_clean_cuts=""
test_other_cuts=""
merged_test_cuts=""
dev_clean_cuts=""
dev_other_cuts=""
merged_dev_cuts=""

run_stamp=auto
run_id=auto
exp_root=""
exp_dir=""
master_port=12460

world_size=8
num_epochs=10
max_duration=1000
ref_duration=600
num_workers=24
num_buckets=30
base_lr=0.045
save_every_n=5000
keep_last_k=-1
average_period=200
valid_interval=1000

use_fp16=true
tensorboard=true
use_wandb=true
wandb_project=emilia-asr
wandb_group=en-h200
wandb_run_name=emilia-en-24k-h200-md1000
wandb_tags=emilia,en,24k,h200,bpe500,md1000
wandb_resume=allow

. "${PARSE_OPTIONS_SH}" || exit 1

if [ -z "${artifact_root}" ]; then
  artifact_root="${public_root}/emilia/fc71e07/icefall_emilia_en_24k"
fi

if [ -n "${dev_clean_cuts}" ] && [ -z "${test_clean_cuts}" ]; then
  test_clean_cuts="${dev_clean_cuts}"
fi

if [ -n "${dev_other_cuts}" ] && [ -z "${test_other_cuts}" ]; then
  test_other_cuts="${dev_other_cuts}"
fi

if [ -n "${merged_dev_cuts}" ] && [ -z "${merged_test_cuts}" ]; then
  merged_test_cuts="${merged_dev_cuts}"
fi

if [ -z "${test_clean_cuts}" ]; then
  test_clean_cuts="${bench_root}/LIBRISPEECH_TEST_CLEAN/fbank/LIBRISPEECH_TEST_CLEAN_cuts.jsonl.gz"
fi

if [ -z "${test_other_cuts}" ]; then
  test_other_cuts="${bench_root}/LIBRISPEECH_TEST_OTHER/fbank/LIBRISPEECH_TEST_OTHER_cuts.jsonl.gz"
fi

if [ -z "${merged_test_cuts}" ]; then
  # Default training-time validation merges LibriSpeech TEST_CLEAN + TEST_OTHER.
  merged_test_cuts="${artifact_root}/eval_assets/librispeech/LIBRISPEECH_TEST_CLEAN_OTHER_cuts.jsonl.gz"
fi

if [ "${run_stamp}" = auto ]; then
  run_stamp="$(date -u '+%Y%m%d_%H%M%S')"
fi

if [ "${run_id}" = auto ]; then
  run_id="$(date -u '+%Y%m%d-%H%M%S')"
fi

if [ -z "${exp_root}" ]; then
  # Keep the EN formal-training base dir parallel to the ZH convention.
  exp_root="${artifact_root}/exp/zipformer/emilia-en-24k-h200-md1000"
fi

if [ -z "${exp_dir}" ]; then
  # Per-run outputs live under: ${exp_root}/full.en.<run_stamp>/run-<run_id>
  exp_dir="${exp_root}/full.en.${run_stamp}/run-${run_id}"
fi

train_cuts="${artifact_root}/data/fbank/en/emilia_en_cuts_train.jsonl.gz"
lang_dir="${artifact_root}/data/lang_bpe_en_500"
bpe_model="${lang_dir}/bpe.model"

if [ ! -f "${train_cuts}" ]; then
  echo "$0: Missing train cuts at ${train_cuts}"
  echo "$0: Run the EN data pipeline first, for example:"
  echo "  bash ${SCRIPT_DIR}/run_cluster_host_pipeline.sh --language en --dataset-root ${dataset_root} --artifact-root ${artifact_root}"
  exit 1
fi

if [ ! -f "${bpe_model}" ]; then
  echo "$0: Missing BPE model at ${bpe_model}"
  echo "$0: Stage 10 must complete before training."
  exit 1
fi

if [ ! -f "${merged_test_cuts}" ]; then
  python3 "${SCRIPT_DIR}/local/merge_lhotse_cuts.py" \
    --output "${merged_test_cuts}" \
    "${test_clean_cuts}" \
    "${test_other_cuts}"
fi

mkdir -p "${exp_dir}"

exec python3 "${SCRIPT_DIR}/zipformer/train.py" \
  --language en \
  --artifact-root "${artifact_root}" \
  --exp-dir "${exp_dir}" \
  --world-size "${world_size}" \
  --master-port "${master_port}" \
  --num-epochs "${num_epochs}" \
  --max-duration "${max_duration}" \
  --ref-duration "${ref_duration}" \
  --num-workers "${num_workers}" \
  --num-buckets "${num_buckets}" \
  --bucketing-sampler true \
  --shuffle true \
  --drop-last true \
  --enable-spec-aug true \
  --enable-musan false \
  --base-lr "${base_lr}" \
  --lr-batches 7500 \
  --lr-epochs 1 \
  --use-fp16 "${use_fp16}" \
  --tensorboard "${tensorboard}" \
  --use-wandb "${use_wandb}" \
  --wandb-project "${wandb_project}" \
  --wandb-group "${wandb_group}" \
  --wandb-run-name "${wandb_run_name}" \
  --wandb-tags "${wandb_tags}" \
  --wandb-resume "${wandb_resume}" \
  --save-every-n "${save_every_n}" \
  --keep-last-k "${keep_last_k}" \
  --average-period "${average_period}" \
  --valid-interval "${valid_interval}" \
  --dev-cuts-path "${merged_test_cuts}"
