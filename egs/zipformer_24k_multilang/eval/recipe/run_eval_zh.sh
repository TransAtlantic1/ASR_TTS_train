#!/usr/bin/env bash
#
# Evaluate the current public Emilia ZH checkpoints on the already prepared
# Chinese eval sets. This wrapper mirrors the iter-based polling semantics of
# the existing auto-decode watcher, but fans out the eval workload across two
# local GPUs and keeps a normalized summary CSV.

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ICEFALL_ROOT=$(cd -- "${SCRIPT_DIR}/../../../.." && pwd)
PARSE_OPTIONS_SH="${ICEFALL_ROOT}/icefall/shared/parse_options.sh"

PUBLIC_ARTIFACT_ROOT="/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public/emilia/fc71e07/icefall_emilia_zh_24k"
DEFAULT_EXP_ROOT="${PUBLIC_ARTIFACT_ROOT}/exp/zipformer/emilia-zh-24k-h200-md1000/full.zh.20260414_191852"
DEFAULT_RESULTS_ROOT="${PUBLIC_ARTIFACT_ROOT}/eval_results/zh_public_current_avg1"
DEFAULT_TEST_SETS="wenetspeech_test_net,wenetspeech_test_meeting"
DEFAULT_GPU0_TEST_SETS="wenetspeech_test_meeting"
DEFAULT_GPU1_TEST_SETS="wenetspeech_test_net"
FEATURE_RUNNER="${SCRIPT_DIR}/../utils/run_eval.py"

bench_root="/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public/eval"
results_root="${DEFAULT_RESULTS_ROOT}"
mode="watch"
test_sets="${DEFAULT_TEST_SETS}"
test_set_preset=""
ref_modes="raw,normalized"
exp_dir="${DEFAULT_EXP_ROOT}"
artifact_root="${PUBLIC_ARTIFACT_ROOT}"
manifest_dir=""
lang_dir=""
bpe_model=""
avg=1
beam_size=4
decoding_methods="greedy_search,modified_beam_search"
decode_every_n=5000
poll_seconds=120
decode_max_duration=1000
decode_num_workers=0
decode_cuda_visible_devices="0,1"
use_averaged_model=true
start_iter=0
iter=0
epoch=0
state_dir=""
log_path=""
train_done_marker=""
once=false
dry_run=false
auto_resolve_run_dir=true
skip_unavailable=false

. "${PARSE_OPTIONS_SH}" || exit 1

trim_spaces() {
  printf '%s' "$1" | tr -d '[:space:]'
}

is_true() {
  case "$(trim_spaces "${1:-false}" | tr '[:upper:]' '[:lower:]')" in
    1|true|t|yes|y) return 0 ;;
    *) return 1 ;;
  esac
}

parse_csv_into_array() {
  local input="$1"
  local -n output_ref="$2"
  local item=""
  local -a raw_items=()

  output_ref=()
  IFS=',' read -r -a raw_items <<<"${input}"
  for item in "${raw_items[@]}"; do
    item="$(trim_spaces "${item}")"
    if [ -n "${item}" ]; then
      output_ref+=("${item}")
    fi
  done
}

join_csv() {
  local -n input_ref="$1"
  local IFS=','
  printf '%s' "${input_ref[*]}"
}

checkpoint_iter_from_path() {
  local checkpoint_path="$1"
  local checkpoint_name
  checkpoint_name="$(basename -- "${checkpoint_path}")"
  if [[ "${checkpoint_name}" =~ ^checkpoint-([0-9]+)\.pt$ ]]; then
    printf '%s\n' "${BASH_REMATCH[1]}"
    return 0
  fi
  return 1
}

resolve_watch_dir() {
  local base_dir="$1"
  local latest_run_dir=""
  local candidate=""
  local base_name=""

  base_name="$(basename -- "${base_dir}")"

  if compgen -G "${base_dir}/checkpoint-*.pt" >/dev/null; then
    printf '%s\n' "${base_dir}"
    return 0
  fi

  if [ -d "${base_dir}" ] && [[ "${base_name}" == run-* ]]; then
    printf '%s\n' "${base_dir}"
    return 0
  fi

  if is_true "${auto_resolve_run_dir}" && [ -d "${base_dir}" ]; then
    while IFS= read -r candidate; do
      latest_run_dir="${candidate}"
    done < <(find "${base_dir}" -maxdepth 1 -mindepth 1 -type d -name 'run-*' | sort)
  fi

  if [ -n "${latest_run_dir}" ]; then
    printf '%s\n' "${latest_run_dir}"
  else
    printf '%s\n' "${base_dir}"
  fi
}

eligible_iters() {
  local actual_exp_dir="$1"
  local effective_start_iter="$2"
  local iter_value=""
  local checkpoint_path=""
  local checkpoint_count=0
  local required_checkpoint_count="${avg}"
  local -a checkpoint_paths=()

  if is_true "${use_averaged_model}"; then
    required_checkpoint_count=$((avg + 1))
  fi

  while IFS= read -r checkpoint_path; do
    checkpoint_paths+=("${checkpoint_path}")
  done < <(find "${actual_exp_dir}" -maxdepth 1 -type f -name 'checkpoint-*.pt' | sort -V)

  checkpoint_count="${#checkpoint_paths[@]}"
  if [ "${checkpoint_count}" -eq 0 ]; then
    return 0
  fi

  for ((i = 0; i < checkpoint_count; ++i)); do
    iter_value="$(checkpoint_iter_from_path "${checkpoint_paths[$i]}")"

    if [ "${iter_value}" -lt "${effective_start_iter}" ]; then
      continue
    fi

    if [ "${decode_every_n}" -gt 0 ] && (( iter_value % decode_every_n != 0 )); then
      continue
    fi

    if (( i + 1 < required_checkpoint_count )); then
      continue
    fi

    printf '%s\n' "${iter_value}"
  done
}

log() {
  printf '[%s] %s\n' "$(date -u '+%Y-%m-%d %H:%M:%S UTC')" "$*" >>"${log_path}"
}

normalized_test_sets="$(trim_spaces "${test_sets}")"

if [ "${avg}" -lt 1 ]; then
  echo "$0: --avg must be >= 1"
  exit 1
fi

if [ "${beam_size}" -lt 1 ]; then
  echo "$0: --beam-size must be >= 1"
  exit 1
fi

if [ "${decode_every_n}" -lt 0 ]; then
  echo "$0: --decode-every-n must be >= 0"
  exit 1
fi

if [ "${poll_seconds}" -lt 1 ]; then
  echo "$0: --poll-seconds must be >= 1"
  exit 1
fi

if [ "${decode_num_workers}" -lt 0 ]; then
  echo "$0: --decode-num-workers must be >= 0"
  exit 1
fi

if [ "${decode_max_duration}" -le 0 ]; then
  echo "$0: --decode-max-duration must be > 0"
  exit 1
fi

if [ "${start_iter}" -lt 0 ]; then
  echo "$0: --start-iter must be >= 0"
  exit 1
fi

if [ -z "${exp_dir}" ]; then
  echo "$0: --exp-dir is required"
  exit 1
fi

if [ "${results_root}" = "${DEFAULT_RESULTS_ROOT}" ] && [ "${artifact_root}" != "${PUBLIC_ARTIFACT_ROOT}" ]; then
  results_root="${artifact_root}/eval_results/zh_public_current_avg1"
fi

hash_input="${exp_dir}|${results_root}|${test_sets}|${test_set_preset}|${decoding_methods}|${ref_modes}"
if [ -z "${state_dir}" ]; then
  state_hash="$(printf '%s' "${hash_input}" | cksum | awk '{print $1}')"
  state_dir="/tmp/icefall-auto-eval/zh-${state_hash}"
fi
mkdir -p "${state_dir}"

if [ -z "${log_path}" ]; then
  log_path="${state_dir}/watcher.log"
fi

lock_dir="${state_dir}/lock"
if ! mkdir "${lock_dir}" 2>/dev/null; then
  echo "$0: another watcher is already using state_dir=${state_dir}"
  exit 1
fi

cleanup() {
  rmdir "${lock_dir}" 2>/dev/null || true
}
trap cleanup EXIT

completed_steps_file="${state_dir}/completed_steps.tsv"
resolved_run_dir_file="${state_dir}/resolved_run_dir.txt"
summary_csv="${results_root}/summary/normalized_by_step.csv"
summary_lock_dir="${state_dir}/summary.lock"
touch "${completed_steps_file}"

declare -a requested_datasets=()
declare -a requested_methods=()
declare -a requested_devices=()
parse_csv_into_array "${test_sets}" requested_datasets
parse_csv_into_array "${decoding_methods}" requested_methods
parse_csv_into_array "${decode_cuda_visible_devices}" requested_devices

if [ "${#requested_methods[@]}" -eq 0 ]; then
  echo "$0: no decoding methods configured"
  exit 1
fi

declare -a worker_labels=()
declare -a worker_dataset_csvs=()
declare -a worker_devices=()

build_dataset_workers() {
  local -a even_datasets=()
  local -a odd_datasets=()
  local dataset=""
  local single_device=""

  worker_labels=()
  worker_dataset_csvs=()
  worker_devices=()

  if [ "${#requested_devices[@]}" -eq 0 ]; then
    requested_devices=("0")
  fi

  single_device="${requested_devices[0]}"

  if [ "${#requested_devices[@]}" -lt 2 ] || [ "${#requested_datasets[@]}" -lt 2 ] || [ -z "${test_sets}" ]; then
    worker_labels=("single")
    worker_dataset_csvs=("$(join_csv requested_datasets)")
    worker_devices=("${single_device}")
    return
  fi

  if [ "${normalized_test_sets}" = "$(trim_spaces "${DEFAULT_TEST_SETS}")" ]; then
    worker_labels=("gpu0" "gpu1")
    worker_dataset_csvs=("${DEFAULT_GPU0_TEST_SETS}" "${DEFAULT_GPU1_TEST_SETS}")
    worker_devices=("${requested_devices[0]}" "${requested_devices[1]}")
    return
  fi

  for ((i = 0; i < ${#requested_datasets[@]}; ++i)); do
    dataset="${requested_datasets[$i]}"
    if (( i % 2 == 0 )); then
      even_datasets+=("${dataset}")
    else
      odd_datasets+=("${dataset}")
    fi
  done

  worker_labels=("gpu0")
  worker_dataset_csvs=("$(join_csv even_datasets)")
  worker_devices=("${requested_devices[0]}")

  if [ "${#odd_datasets[@]}" -gt 0 ]; then
    worker_labels+=("gpu1")
    worker_dataset_csvs+=("$(join_csv odd_datasets)")
    worker_devices+=("${requested_devices[1]}")
  fi
}

step_key() {
  local iter_value="$1"
  local epoch_value="$2"
  if [ "${iter_value}" -gt 0 ]; then
    printf 'iter:%s' "${iter_value}"
  else
    printf 'epoch:%s' "${epoch_value}"
  fi
}

step_label() {
  local iter_value="$1"
  local epoch_value="$2"
  if [ "${iter_value}" -gt 0 ]; then
    printf 'iter-%s' "${iter_value}"
  else
    printf 'epoch-%s' "${epoch_value}"
  fi
}

dataset_step_already_done() {
  local dataset_id="$1"
  local iter_value="$2"
  local epoch_value="$3"
  local key=""

  key="$(step_key "${iter_value}" "${epoch_value}")"
  grep -Fqx "${dataset_id}	${key}" "${completed_steps_file}"
}

mark_dataset_step_done() {
  local dataset_id="$1"
  local iter_value="$2"
  local epoch_value="$3"
  local key=""

  key="$(step_key "${iter_value}" "${epoch_value}")"
  if ! dataset_step_already_done "${dataset_id}" "${iter_value}" "${epoch_value}"; then
    printf '%s\t%s\n' "${dataset_id}" "${key}" >>"${completed_steps_file}"
  fi
}

iter_fully_done() {
  local iter_value="$1"
  local epoch_value="$2"
  local dataset_id=""

  for dataset_id in "${requested_datasets[@]}"; do
    if ! dataset_step_already_done "${dataset_id}" "${iter_value}" "${epoch_value}"; then
      return 1
    fi
  done
  return 0
}

aggregate_normalized_csv() {
  local requested_dataset_csv=""
  local requested_method_csv=""
  local lock_acquired=false
  local status=0

  if is_true "${dry_run}"; then
    return 0
  fi

  while ! mkdir "${summary_lock_dir}" 2>/dev/null; do
    sleep 1
  done
  lock_acquired=true

  requested_dataset_csv="$(join_csv requested_datasets)"
  requested_method_csv="$(join_csv requested_methods)"

  python3 - "${results_root}" "${summary_csv}" "${requested_dataset_csv}" "${requested_method_csv}" <<'PY' || status=$?
import csv
import json
import sys
from pathlib import Path

results_root = Path(sys.argv[1])
summary_csv = Path(sys.argv[2])
dataset_order = [item for item in sys.argv[3].split(",") if item]
method_order = [item for item in sys.argv[4].split(",") if item]

rows = {}
columns_seen = set()

for metrics_path in sorted(results_root.glob("dataset_*/_summary/*.metrics.jsonl")):
    stem = metrics_path.name
    if not stem.endswith(".metrics.jsonl"):
        continue
    stem = stem[: -len(".metrics.jsonl")]
    if stem.startswith("iter-"):
        step = stem[len("iter-") :]
    elif stem.startswith("epoch-"):
        step = stem
    else:
        continue

    row = rows.setdefault(step, {})
    with open(metrics_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            if item.get("metric") != "normalized-plain":
                continue
            column = f"{item['dataset_id']}__{item['method']}__normalized"
            row[column] = item.get("value", "")
            columns_seen.add(column)

if dataset_order:
    columns = [
        f"{dataset_id}__{method}__normalized"
        for dataset_id in dataset_order
        for method in method_order
    ]
else:
    columns = sorted(columns_seen)

def step_sort_key(step: str):
    return (0, int(step)) if step.isdigit() else (1, step)

summary_csv.parent.mkdir(parents=True, exist_ok=True)
with open(summary_csv, "w", encoding="utf-8", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["step", *columns])
    for step in sorted(rows, key=step_sort_key):
        writer.writerow([step, *[rows[step].get(column, "") for column in columns]])
PY

  if [ "${lock_acquired}" = true ]; then
    rmdir "${summary_lock_dir}" 2>/dev/null || true
  fi
  return "${status}"
}

run_one_dataset_eval() {
  local actual_exp_dir="$1"
  local dataset_id="$2"
  local worker_label="$3"
  local worker_device="$4"
  local iter_value="$5"
  local epoch_value="$6"
  local dataset_results_root=""
  local current_step_label=""
  local dataset_log=""
  local -a cmd=()

  if [ -z "${dataset_id}" ] && [ -z "${test_set_preset}" ]; then
    log "skip empty dataset worker=${worker_label}"
    return 0
  fi

  if dataset_step_already_done "${dataset_id}" "${iter_value}" "${epoch_value}"; then
    return 0
  fi

  current_step_label="$(step_label "${iter_value}" "${epoch_value}")"
  dataset_results_root="${results_root}/dataset_${dataset_id}"
  dataset_log="${state_dir}/${current_step_label}-${dataset_id}.log"
  mkdir -p "${dataset_results_root}"

  cmd=(
    python3 "${FEATURE_RUNNER}"
    --language zh
    --mode once
    --bench-root "${bench_root}"
    --results-root "${dataset_results_root}"
    --ref-modes "${ref_modes}"
    --exp-dir "${actual_exp_dir}"
    --artifact-root "${artifact_root}"
    --manifest-dir "${manifest_dir}"
    --lang-dir "${lang_dir}"
    --bpe-model "${bpe_model}"
    --avg "${avg}"
    --beam-size "${beam_size}"
    --decoding-methods "${decoding_methods}"
    --decode-every-n "${decode_every_n}"
    --poll-seconds "${poll_seconds}"
    --decode-max-duration "${decode_max_duration}"
    --decode-num-workers "${decode_num_workers}"
    --use-averaged-model "${use_averaged_model}"
    --start-iter "${start_iter}"
    --iter "${iter_value}"
    --epoch "${epoch_value}"
    --state-dir ""
    --log-path ""
    --train-done-marker ""
    --once false
    --dry-run false
    --auto-resolve-run-dir "${auto_resolve_run_dir}"
    --skip-unavailable "${skip_unavailable}"
  )

  if [ -n "${dataset_id}" ]; then
    cmd+=(--test-sets "${dataset_id}" --test-set-preset "")
  else
    cmd+=(--test-sets "" --test-set-preset "${test_set_preset}")
  fi

  if [ -n "${worker_device}" ]; then
    cmd+=(--decode-cuda-visible-devices "${worker_device}")
  fi

  log "starting ${current_step_label} dataset=${dataset_id} worker=${worker_label} device=${worker_device:-<default>}"
  log "command: $(printf '%q ' "${cmd[@]}")"

  if is_true "${dry_run}"; then
    return 0
  fi

  if "${cmd[@]}" >"${dataset_log}" 2>&1; then
    mark_dataset_step_done "${dataset_id}" "${iter_value}" "${epoch_value}"
    aggregate_normalized_csv
    log "finished ${current_step_label} dataset=${dataset_id} worker=${worker_label} log=${dataset_log}"
    return 0
  fi

  log "failed ${current_step_label} dataset=${dataset_id} worker=${worker_label} log=${dataset_log}"
  return 1
}

run_worker_queue() {
  local actual_exp_dir="$1"
  local worker_label="$2"
  local worker_dataset_csv="$3"
  local worker_device="$4"
  local pending_iter_csv="$5"
  local dataset_id=""
  local iter_value=""
  local -a pids=()
  local -a worker_datasets=()
  local -a pending_iters=()

  parse_csv_into_array "${worker_dataset_csv}" worker_datasets
  parse_csv_into_array "${pending_iter_csv}" pending_iters

  for dataset_id in "${worker_datasets[@]}"; do
    for iter_value in "${pending_iters[@]}"; do
      if ! run_one_dataset_eval "${actual_exp_dir}" "${dataset_id}" "${worker_label}" "${worker_device}" "${iter_value}" 0; then
        return 1
      fi
    done
  done

  return 0
}

run_pending_iters() {
  local actual_exp_dir="$1"
  shift
  local wait_status=0
  local worker_label=""
  local worker_dataset_csv=""
  local worker_device=""
  local pending_iter_csv=""
  local -a pids=()

  build_dataset_workers
  mkdir -p "${results_root}"
  pending_iter_csv="$(printf '%s\n' "$@" | paste -sd, -)"

  for ((i = 0; i < ${#worker_labels[@]}; ++i)); do
    worker_label="${worker_labels[$i]}"
    worker_dataset_csv="${worker_dataset_csvs[$i]}"
    worker_device="${worker_devices[$i]}"
    run_worker_queue "${actual_exp_dir}" "${worker_label}" "${worker_dataset_csv}" "${worker_device}" "${pending_iter_csv}" &
    pids+=("$!")
  done

  for pid in "${pids[@]}"; do
    if ! wait "${pid}"; then
      wait_status=1
    fi
  done

  return "${wait_status}"
}

run_once() {
  local resolved_exp_dir=""
  local -a current_eligible=()
  local -a pending_iters=()
  local iter_value=""
  local index=0

  resolved_exp_dir="$(resolve_watch_dir "${exp_dir}")"
  printf '%s\n' "${resolved_exp_dir}" >"${resolved_run_dir_file}"
  log "resolved run dir: ${resolved_exp_dir}"

  if [ "${epoch}" -gt 0 ]; then
    for iter_value in "${requested_datasets[@]}"; do
      run_one_dataset_eval "${resolved_exp_dir}" "${iter_value}" "single" "${requested_devices[0]:-0}" 0 "${epoch}"
    done
    return
  fi

  if [ "${iter}" -gt 0 ]; then
    run_pending_iters "${resolved_exp_dir}" "${iter}"
    return
  fi

  while IFS= read -r iter_value; do
    current_eligible+=("${iter_value}")
  done < <(eligible_iters "${resolved_exp_dir}" "${start_iter}")

  if [ "${#current_eligible[@]}" -eq 0 ]; then
    echo "$0: no eligible checkpoints found under ${resolved_exp_dir}"
    exit 1
  fi

  pending_iters=()
  for ((index = ${#current_eligible[@]} - 1; index >= 0; --index)); do
    iter_value="${current_eligible[$index]}"
    if iter_fully_done "${iter_value}" 0; then
      continue
    fi
    pending_iters+=("${iter_value}")
  done

  if [ "${#pending_iters[@]}" -gt 0 ]; then
    run_pending_iters "${resolved_exp_dir}" "${pending_iters[@]}"
  fi
}

watch_loop() {
  local resolved_exp_dir=""
  local pending_found=false
  local iter_value=""
  local index=0
  local -a current_eligible=()
  local -a pending_iters=()

  log "watcher started base_exp_dir=${exp_dir} state_dir=${state_dir}"
  log "settings: avg=${avg} decode_every_n=${decode_every_n} poll_seconds=${poll_seconds} start_iter=${start_iter} methods=${decoding_methods} devices=${decode_cuda_visible_devices}"

  while true; do
    if [ -z "${resolved_exp_dir}" ]; then
      resolved_exp_dir="$(resolve_watch_dir "${exp_dir}")"
      printf '%s\n' "${resolved_exp_dir}" >"${resolved_run_dir_file}"
      log "resolved run dir: ${resolved_exp_dir}"
    fi

    while IFS= read -r iter_value; do
      current_eligible+=("${iter_value}")
    done < <(eligible_iters "${resolved_exp_dir}" "${start_iter}")

    pending_iters=()
    pending_found=false
    for ((index = ${#current_eligible[@]} - 1; index >= 0; --index)); do
      iter_value="${current_eligible[$index]}"
      if iter_fully_done "${iter_value}" 0; then
        continue
      fi
      pending_found=true
      pending_iters+=("${iter_value}")
    done
    current_eligible=()

    if [ "${#pending_iters[@]}" -gt 0 ]; then
      if ! run_pending_iters "${resolved_exp_dir}" "${pending_iters[@]}"; then
        log "will retry pending datasets on the next poll"
      fi
    fi

    if [ -n "${train_done_marker}" ] && [ -e "${train_done_marker}" ] && [ "${pending_found}" = false ]; then
      log "train_done_marker detected and no pending eval remains; exiting"
      break
    fi

    if is_true "${once}"; then
      break
    fi

    sleep "${poll_seconds}"
  done

  log "watcher stopped"
}

if [ "${mode}" = "once" ] || is_true "${once}"; then
  run_once
else
  watch_loop
fi
