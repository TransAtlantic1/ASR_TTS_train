#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ICEFALL_ROOT=$(cd -- "${SCRIPT_DIR}/../../../.." && pwd)
RECIPE_ROOT=$(cd -- "${SCRIPT_DIR}/../.." && pwd)
PARSE_OPTIONS_SH="${ICEFALL_ROOT}/icefall/shared/parse_options.sh"
DATA_CONFIG_SH="${RECIPE_ROOT}/data_config/load_data_config.sh"
DATA_CONFIG_LOADER="${RECIPE_ROOT}/data_config/load_yaml_config.py"

language=en
data_config=""
dataset=""
dataset_name=emilia
dataset_id=fc71e07
manifest_prefix=""
lang_dir_name=""
manifest_dir=""
fbank_dir=""
public_root=/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public
dataset_root=""
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
on_the_fly_feats=false

use_fp16=true
tensorboard=true
use_wandb=true
wandb_project=emilia-asr
wandb_group=en-h200
wandb_run_name=emilia-en-24k-h200-md1000
wandb_tags=emilia,en,24k,h200,bpe500,md1000
wandb_resume=allow

ORIGINAL_ARGS=("$@")
. "${PARSE_OPTIONS_SH}" || exit 1
. "${DATA_CONFIG_SH}"
if [ -n "$dataset" ]; then
  dataset_name="$dataset"
fi
if [ -z "$data_config" ]; then
  data_config=$(default_data_config "$RECIPE_ROOT" "$dataset_name" "$language")
fi
load_data_config "$data_config" "$DATA_CONFIG_LOADER"
set -- "${ORIGINAL_ARGS[@]}"
. "${PARSE_OPTIONS_SH}" || exit 1

if [ -n "$dataset" ]; then
  dataset_name="$dataset"
else
  dataset="$dataset_name"
fi
if [ -z "${artifact_root}" ]; then
  artifact_root="${public_root}/${dataset_name}/${dataset_id}/icefall_${dataset_name}_${language}_24k"
fi
if [ -z "$manifest_prefix" ]; then
  manifest_prefix="${dataset_name}_${language}"
fi
if [ -z "$lang_dir_name" ]; then
  lang_dir_name=lang_bpe_en_500
fi
if [ -z "${manifest_dir}" ]; then
  if [ -n "${fbank_dir}" ]; then
    manifest_dir="${fbank_dir}"
  else
    manifest_dir="${artifact_root}/data/fbank/${language}"
  fi
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
  exp_root="${artifact_root}/exp/zipformer/${dataset_name}-en-24k-h200-md1000"
fi

if [ -z "${exp_dir}" ]; then
  # Per-run outputs live under: ${exp_root}/full.en.<run_stamp>/run-<run_id>
  exp_dir="${exp_root}/full.en.${run_stamp}/run-${run_id}"
fi

train_cuts="${manifest_dir}/${manifest_prefix}_cuts_train.jsonl.gz"
train_cut_candidates=("${train_cuts}")
train_split_patterns=("${manifest_prefix}_cuts_train.*.jsonl.gz")
if [ "${on_the_fly_feats}" = true ]; then
  train_cut_candidates=(
    "${manifest_dir}/${manifest_prefix}_cuts_train_raw.jsonl.gz"
  )
  train_split_patterns=()
fi
train_cuts_probe=""
for candidate in "${train_cut_candidates[@]}"; do
  if [ -f "${candidate}" ]; then
    train_cuts_probe="${candidate}"
    break
  fi
done
train_split_probe=""
for pattern in "${train_split_patterns[@]}"; do
  train_split_probe=$(
    find "${manifest_dir}" \
      -path "*/train_split_*/${pattern}" \
      -print -quit 2>/dev/null || true
  )
  if [ -n "${train_split_probe}" ]; then
    break
  fi
done
lang_dir="${artifact_root}/data/${lang_dir_name}"
bpe_model="${lang_dir}/bpe.model"

if [ -z "${train_cuts_probe}" ] && [ -z "${train_split_probe}" ]; then
  echo "$0: Missing train cuts. Checked:"
  for candidate in "${train_cut_candidates[@]}"; do
    echo "  ${candidate}"
  done
  if [ "${#train_split_patterns[@]}" -gt 0 ]; then
    echo "$0: Also found no split train cuts under ${manifest_dir}/train_split_*"
  fi
  echo "$0: Run the EN data pipeline first, for example:"
  echo "  bash ${SCRIPT_DIR}/run_cluster_pipeline.sh --role host --language en --data-config ${data_config}"
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
  --dataset "${dataset}" \
  --artifact-root "${artifact_root}" \
  --manifest-dir "${manifest_dir}" \
  --manifest-prefix "${manifest_prefix}" \
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
  --on-the-fly-feats "${on_the_fly_feats}" \
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
