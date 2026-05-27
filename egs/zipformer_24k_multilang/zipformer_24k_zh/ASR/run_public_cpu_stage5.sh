#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
SCRIPT_SELF="${SCRIPT_DIR}/$(basename -- "${BASH_SOURCE[0]}")"
ICEFALL_ROOT=$(cd -- "${SCRIPT_DIR}/../../../.." && pwd)
RECIPE_ROOT=$(cd -- "${SCRIPT_DIR}/../.." && pwd)
PARSE_OPTIONS_SH="${ICEFALL_ROOT}/icefall/shared/parse_options.sh"
DATA_CONFIG_SH="${RECIPE_ROOT}/data_config/load_data_config.sh"
DATA_CONFIG_LOADER="${RECIPE_ROOT}/data_config/load_yaml_config.py"

language=zh
data_config=""
dataset_name=emilia
dataset_id=fc71e07
public_root=/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public
dataset_root=""
artifact_root=""
feature_num_workers=20
feature_batch_duration=1000
feature_device=cpu
log_root=""
detach=false
detach_log=""

ORIGINAL_ARGS=("$@")
. "${PARSE_OPTIONS_SH}" || exit 1
. "${DATA_CONFIG_SH}"
if [ -z "$data_config" ]; then
  data_config=$(default_data_config "$RECIPE_ROOT" "$dataset_name" "$language")
fi
load_data_config "$data_config" "$DATA_CONFIG_LOADER"
set -- "${ORIGINAL_ARGS[@]}"
. "${PARSE_OPTIONS_SH}" || exit 1

if [[ "$language" != "zh" && "$language" != "en" ]]; then
  echo "$0: --language must be one of zh or en, got: $language"
  exit 1
fi

if [ -z "$dataset_root" ]; then
  echo "$0: dataset_root is empty; set it in --data-config or pass --dataset-root"
  exit 1
fi

if [ -z "$artifact_root" ]; then
  artifact_root="${public_root%/}/${dataset_name}/${dataset_id}/icefall_${dataset_name}_${language}_24k"
fi

if [ -z "$log_root" ]; then
  log_root="${artifact_root}/logs"
fi

mkdir -p "$log_root"

log_file="${log_root}/feature.cpu.stage5.${language}.log"
if [ -z "$detach_log" ]; then
  detach_log="${log_root}/launcher.feature.cpu.stage5.${language}.nohup.log"
fi

if [ "$detach" = true ]; then
  cmd=(
    "${SCRIPT_SELF}"
    --language "$language"
    --data-config "$data_config"
    --public-root "$public_root"
    --dataset-root "$dataset_root"
    --artifact-root "$artifact_root"
    --feature-num-workers "$feature_num_workers"
    --feature-batch-duration "$feature_batch_duration"
    --feature-device "$feature_device"
    --log-root "$log_root"
    --detach false
    --detach-log "$detach_log"
  )
  nohup "${cmd[@]}" >>"$detach_log" 2>&1 &
  pid=$!
  echo "$0: detached pid=${pid}"
  echo "$0: launcher_log=${detach_log}"
  echo "$0: worker_log=${log_file}"
  exit 0
fi

echo "$0: language=${language}"
echo "$0: dataset_root=${dataset_root}"
echo "$0: artifact_root=${artifact_root}"
echo "$0: feature_device=${feature_device}"
echo "$0: detach_log=${detach_log}"
echo "$0: log_file=${log_file}"

exec env CUDA_VISIBLE_DEVICES="" bash "${SCRIPT_DIR}/prepare.sh" \
  --language "$language" \
  --data-config "$data_config" \
  --dataset-root "$dataset_root" \
  --artifact-root "$artifact_root" \
  --feature-device "$feature_device" \
  --feature-num-workers "$feature_num_workers" \
  --feature-batch-duration "$feature_batch_duration" \
  --stage 5 \
  --stop-stage 5 \
  >>"$log_file" 2>&1
