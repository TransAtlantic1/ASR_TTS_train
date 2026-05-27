#!/usr/bin/env bash

export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ICEFALL_ROOT=$(cd -- "${SCRIPT_DIR}/../../.." && pwd)
PARSE_OPTIONS_SH="${ICEFALL_ROOT}/icefall/shared/parse_options.sh"
RECIPE_DIR="${RECIPE_DIR:-${ICEFALL_ROOT}/egs/zipformer_24k_multilang/zipformer_24k_en/ASR}"
VALIDATION_ROOT="${VALIDATION_ROOT:-$(cd -- "${ICEFALL_ROOT}/.." && pwd)/experiments/main_flow_validation/emilia24k_en}"

mode=prepare-subset
language=en
artifact_root="${VALIDATION_ROOT}/workspace/artifacts"
train_split_name="train_split_4"
train_shard_ids="0000"
subset_name=""
subset_root="${VALIDATION_ROOT}/workspace/subset"
eval_assets_root="${VALIDATION_ROOT}/workspace/eval_assets"
dev_cuts_source="/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public/eval/LIBRISPEECH_TEST_CLEAN/fbank/LIBRISPEECH_TEST_CLEAN_cuts.jsonl.gz"
dev_cuts_path="${eval_assets_root}/LIBRISPEECH_TEST_CLEAN_cuts.jsonl.gz"
run_base="${VALIDATION_ROOT}/exp/smoke"
run_id=""
exp_dir=""
world_size=1
master_port=12460
cuda_visible_devices="0"
num_epochs=1
max_duration=240
num_workers=0
num_buckets=8
bucketing_sampler=false
shuffle=false
drop_last=false
use_wandb=false
tensorboard=false
valid_interval=1

. "${PARSE_OPTIONS_SH}" || exit 1

if [[ "${mode}" != "prepare-subset" && "${mode}" != "smoke" ]]; then
  echo "$0: --mode must be one of prepare-subset or smoke"
  exit 1
fi

if [[ "${language}" != "en" ]]; then
  echo "$0: this helper currently supports only --language en"
  exit 1
fi

manifest_source_dir="${artifact_root}/data/fbank/${language}"
train_split_dir="${manifest_source_dir}/${train_split_name}"
lang_dir="${artifact_root}/data/lang_bpe_en_500"

if [ ! -d "${manifest_source_dir}" ]; then
  echo "$0: missing manifest source dir ${manifest_source_dir}"
  exit 1
fi

if [ ! -d "${train_split_dir}" ]; then
  echo "$0: missing processed train split dir ${train_split_dir}"
  exit 1
fi

if [ ! -d "${lang_dir}" ]; then
  echo "$0: missing lang dir ${lang_dir}"
  exit 1
fi

if [ ! -f "${dev_cuts_source}" ]; then
  echo "$0: missing dev cuts source ${dev_cuts_source}"
  exit 1
fi

if [ -z "${subset_name}" ]; then
  subset_name=$(echo "${train_shard_ids}" | tr ',' '_')
fi

mkdir -p "${subset_root}" "${eval_assets_root}" "${run_base}"

prepare_subset() {
  local split_dir info_file shard_id shard_src shard_dst shard_index

  split_dir="${subset_root}/train_split_subset"
  rm -rf "${split_dir}"
  mkdir -p "${split_dir}"

  IFS=',' read -r -a shard_ids <<<"${train_shard_ids}"
  if [ "${#shard_ids[@]}" -eq 0 ]; then
    echo "$0: no shard ids provided in --train-shard-ids"
    exit 1
  fi

  for shard_id in "${shard_ids[@]}"; do
    shard_index=$((10#${shard_id}))
    shard_src="${train_split_dir}/emilia_${language}_cuts_train.${shard_index}.jsonl.gz"
    if [ ! -f "${shard_src}" ]; then
      shard_src="${train_split_dir}/emilia_${language}_cuts_train.$(printf "%04d" "${shard_index}").jsonl.gz"
    fi
    if [ ! -f "${shard_src}" ]; then
      echo "$0: missing processed shard ${shard_src}"
      exit 1
    fi
    shard_dst="${split_dir}/$(basename "${shard_src}")"
    ln -sfn "${shard_src}" "${shard_dst}"
  done

  ln -sfn "${dev_cuts_source}" "${dev_cuts_path}"

  info_file="${subset_root}/subset_info.txt"
  {
    printf 'created_utc=%s\n' "$(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    printf 'language=%s\n' "${language}"
    printf 'artifact_root=%s\n' "${artifact_root}"
    printf 'manifest_source_dir=%s\n' "${manifest_source_dir}"
    printf 'train_split_dir=%s\n' "${train_split_dir}"
    printf 'train_shard_ids=%s\n' "${train_shard_ids}"
    printf 'subset_root=%s\n' "${subset_root}"
    printf 'dev_cuts_source=%s\n' "${dev_cuts_source}"
    printf 'dev_cuts_path=%s\n' "${dev_cuts_path}"
  } >"${info_file}"

  echo "$0: prepared subset_root=${subset_root}"
  echo "$0: subset_info=${info_file}"
}

prepare_subset

if [ "${mode}" = "prepare-subset" ]; then
  exit 0
fi

if [ -z "${run_id}" ]; then
  run_id="smoke.${language}.subset-${subset_name}.md${max_duration}.$(date +%Y%m%d_%H%M%S)"
fi

if [ -z "${exp_dir}" ]; then
  exp_dir="${run_base}/${run_id}"
fi
mkdir -p "${exp_dir}"

export PYTHONPATH="${ICEFALL_ROOT}:${PYTHONPATH:-}"
export CUDA_VISIBLE_DEVICES="${cuda_visible_devices}"

cmd=(
  python3 zipformer/train.py
  --language "${language}"
  --artifact-root "${artifact_root}"
  --manifest-dir "${subset_root}"
  --lang-dir "${lang_dir}"
  --dev-cuts-path "${dev_cuts_path}"
  --exp-dir "${exp_dir}"
  --world-size "${world_size}"
  --master-port "${master_port}"
  --num-epochs "${num_epochs}"
  --bucketing-sampler "${bucketing_sampler}"
  --shuffle "${shuffle}"
  --drop-last "${drop_last}"
  --use-wandb "${use_wandb}"
  --tensorboard "${tensorboard}"
  --max-duration "${max_duration}"
  --num-workers "${num_workers}"
  --num-buckets "${num_buckets}"
  --valid-interval "${valid_interval}"
)

printf '%q ' "${cmd[@]}" >"${exp_dir}/launch_cmd.txt"
printf '\n' >>"${exp_dir}/launch_cmd.txt"

echo "$0: mode=${mode}"
echo "$0: exp_dir=${exp_dir}"
echo "$0: subset_root=${subset_root}"
echo "$0: lang_dir=${lang_dir}"
echo "$0: dev_cuts_path=${dev_cuts_path}"
echo "$0: train_shard_ids=${train_shard_ids}"
echo "$0: num_epochs=${num_epochs}"
echo "$0: max_duration=${max_duration}"
echo "$0: bucketing_sampler=${bucketing_sampler}"
echo "$0: shuffle=${shuffle}"
echo "$0: drop_last=${drop_last}"
echo "$0: valid_interval=${valid_interval}"

(cd "${RECIPE_DIR}" && stdbuf -oL -eL "${cmd[@]}") 2>&1 | tee "${exp_dir}/launcher.stdout.log"

if [ ! -f "${exp_dir}/epoch-1.pt" ]; then
  echo "$0: missing ${exp_dir}/epoch-1.pt"
  exit 1
fi

if [ ! -f "${exp_dir}/best-valid-loss.pt" ]; then
  echo "$0: missing ${exp_dir}/best-valid-loss.pt"
  exit 1
fi

if ! grep -q "Computing validation loss" "${exp_dir}/launcher.stdout.log"; then
  echo "$0: validation loop did not start according to launcher.stdout.log"
  exit 1
fi

if ! grep -q "Epoch 1, validation:" "${exp_dir}/launcher.stdout.log"; then
  echo "$0: validation loop did not complete according to launcher.stdout.log"
  exit 1
fi

echo "$0: smoke training and dev validation loop completed in ${exp_dir}"
