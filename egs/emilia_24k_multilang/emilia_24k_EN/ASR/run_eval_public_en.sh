#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ICEFALL_ROOT=$(cd -- "${SCRIPT_DIR}/../../../.." && pwd)
PARSE_OPTIONS_SH="${ICEFALL_ROOT}/icefall/shared/parse_options.sh"
SHARED_EVAL_WRAPPER="${ICEFALL_ROOT}/egs/emilia_24k_multilang/eval/recipe/run_eval_en.sh"

public_root=/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public
bench_root="${public_root}/eval"
artifact_root=""
exp_root=""
exp_dir=""
results_root=""
test_set_preset=en-open-v1

avg=3
epoch=10
beam_size=4
decoding_methods=greedy_search,modified_beam_search
decode_max_duration=1000
decode_num_workers=0
decode_cuda_visible_devices=""
use_averaged_model=true

. "${PARSE_OPTIONS_SH}" || exit 1

resolve_latest_run_dir() {
  local base_dir="$1"
  local latest_full=""
  local latest_run=""

  if [ -d "${base_dir}" ]; then
    while IFS= read -r candidate; do
      latest_full="${candidate}"
    done < <(find "${base_dir}" -maxdepth 1 -mindepth 1 -type d -name 'full.en.*' | sort)
  fi

  if [ -n "${latest_full}" ] && [ -d "${latest_full}" ]; then
    while IFS= read -r candidate; do
      latest_run="${candidate}"
    done < <(find "${latest_full}" -maxdepth 1 -mindepth 1 -type d -name 'run-*' | sort)
  fi

  if [ -n "${latest_run}" ]; then
    printf '%s\n' "${latest_run}"
    return 0
  fi

  if [ -n "${latest_full}" ]; then
    printf '%s\n' "${latest_full}"
    return 0
  fi

  return 1
}

if [ -z "${artifact_root}" ]; then
  artifact_root="${public_root}/emilia/fc71e07/icefall_emilia_en_24k"
fi

if [ -z "${exp_root}" ]; then
  exp_root="${artifact_root}/exp/zipformer/emilia-en-24k-h200-md1000"
fi

if [ -z "${exp_dir}" ]; then
  if ! exp_dir="$(resolve_latest_run_dir "${exp_root}")"; then
    echo "$0: Could not auto-resolve a full.en.* run under ${exp_root}"
    exit 1
  fi
fi

if [ -z "${results_root}" ]; then
  results_root="${artifact_root}/eval_results/en_public_current_avg${avg}"
fi

if [ ! -d "${exp_dir}" ]; then
  echo "$0: Missing experiment directory: ${exp_dir}"
  exit 1
fi

exec bash "${SHARED_EVAL_WRAPPER}" \
  --mode once \
  --once true \
  --bench-root "${bench_root}" \
  --results-root "${results_root}" \
  --test-set-preset "${test_set_preset}" \
  --artifact-root "${artifact_root}" \
  --exp-dir "${exp_dir}" \
  --avg "${avg}" \
  --epoch "${epoch}" \
  --beam-size "${beam_size}" \
  --decoding-methods "${decoding_methods}" \
  --decode-max-duration "${decode_max_duration}" \
  --decode-num-workers "${decode_num_workers}" \
  --decode-cuda-visible-devices "${decode_cuda_visible_devices}" \
  --use-averaged-model "${use_averaged_model}"
