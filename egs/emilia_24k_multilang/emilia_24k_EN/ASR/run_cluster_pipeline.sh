#!/usr/bin/env bash

export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python

set -euo pipefail
shopt -s nullglob

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ICEFALL_ROOT=$(cd -- "${SCRIPT_DIR}/../../../.." && pwd)
PARSE_OPTIONS_SH="${ICEFALL_ROOT}/icefall/shared/parse_options.sh"
SELF_PATH="${SCRIPT_DIR}/run_cluster_pipeline.sh"

role=host
supervise=false
supervisor_max_restarts=-1
local_worker_supervise=true

language=en
public_root=/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public
dataset_root=/inspire/dataset/emilia/fc71e07
artifact_root=""
run_id=auto

run_stage10=true
launch_local_worker=true
local_worker_index=0
worker_index=-1

recording_num_splits=1000
feature_num_splits=1000
num_stage7_workers=9
feature_num_workers=24
feature_batch_duration=2000
feature_device=cpu
enable_musan=false
max_jsonl_files=-1
max_utterances=-1

poll_seconds=30
heartbeat_seconds=60
stale_seconds=900
max_attempts=3
retry_backoff_seconds=120
retry_backoff_multiplier=2
retry_backoff_max_seconds=900
retry_jitter_seconds=30

. "${PARSE_OPTIONS_SH}" || exit 1

if [[ "$role" != host && "$role" != worker ]]; then
  echo "$0: --role must be one of host or worker, got: $role"
  exit 1
fi

if [[ "$language" != "zh" && "$language" != "en" ]]; then
  echo "$0: --language must be one of zh or en, got: $language"
  exit 1
fi

if [ -z "$artifact_root" ]; then
  artifact_root="${public_root%/}/emilia/fc71e07/icefall_emilia_${language}_24k"
fi

if [ "$feature_num_splits" -le 0 ] || [ "$num_stage7_workers" -le 0 ]; then
  echo "$0: --feature-num-splits and --num-stage7-workers must be > 0"
  exit 1
fi

if [ "$feature_num_splits" -ne 1000 ] || [ "$recording_num_splits" -ne 1000 ]; then
  echo "$0: this recipe expects --recording-num-splits=1000 and --feature-num-splits=1000"
  exit 1
fi

if [ "$role" = worker ] && { [ "$worker_index" -lt 0 ] || [ "$worker_index" -ge "$num_stage7_workers" ]; }; then
  echo "$0: --worker-index must be in [0, ${num_stage7_workers})"
  exit 1
fi

prefix="emilia_${language}"
data_root="${artifact_root}/data"
fbank_dir="${data_root}/fbank/${language}"
train_feature_split_dir="${fbank_dir}/train_split_${feature_num_splits}"
if [ "$language" = zh ]; then
  lang_dir="${data_root}/lang_bpe_zh_2000"
else
  lang_dir="${data_root}/lang_bpe_en_500"
fi
state_root="${artifact_root}/orchestration/stage4_10/${language}"
current_run_id_file="${state_root}/current_run_id"

run_dir=""
logs_root=""
attempts_root=""
role_log_file=""
stage7_dir=""
stage7_generations_dir=""
stage7_assignment_lock_dir=""
stage7_current_generation_file=""
stage7_done_marker=""
stage7_ready_marker=""
stage7_preparing_lock_dir=""
pipeline_done_marker=""
pipeline_failed_marker=""
host_lock_dir=""
worker_locks_dir=""
worker_lock_dir=""
held_stage7_assignment_lock=false
held_stage7_preparing_lock=false
held_host_lock=false
held_worker_lock=false
local_worker_pid_file=""
local_worker_launcher_log=""
heartbeat_pid=""
lease_keepalive_pid=""
local_worker_pid=""
launched_local_worker=false
supervisor_child_pid=""
created_generation_result=""

declare -a ALL_RAW_SHARD_PATHS=()
declare -A RAW_SHARD_PATH_BY_IDX=()
declare -A RAW_SHARD_PATH_BY_NUM=()

log() {
  local line
  line="[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] $*"
  echo "$line"
  if [ -n "$role_log_file" ]; then
    mkdir -p "$(dirname "$role_log_file")"
    printf '%s\n' "$line" >>"$role_log_file"
  fi
}

write_text_atomic() {
  local path="$1"
  local content="$2"
  local tmp="${path}.tmp.$$.$RANDOM"
  mkdir -p "$(dirname "$path")"
  printf '%s' "$content" >"$tmp"
  mv "$tmp" "$path"
}

write_marker() {
  local path="$1"
  local extra="${2:-}"
  local tmp="${path}.tmp.$$.$RANDOM"
  mkdir -p "$(dirname "$path")"
  {
    printf 'time=%s\n' "$(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    printf 'host=%s\n' "$(hostname)"
    printf 'pid=%s\n' "$$"
    printf 'role=%s\n' "$role"
    if [ "$role" = worker ]; then
      printf 'worker_index=%s\n' "$worker_index"
    fi
    if [ -n "$extra" ]; then
      printf '%s\n' "$extra"
    fi
  } >"$tmp"
  mv "$tmp" "$path"
}

remove_path_if_exists() {
  local path
  for path in "$@"; do
    if [ -e "$path" ] || [ -L "$path" ]; then
      rm -rf "$path"
    fi
  done
}

file_age_seconds() {
  local path="$1"
  local now
  now=$(date +%s)
  echo $((now - $(stat -c '%Y' "$path")))
}

lock_owner_file() {
  local lock_dir="$1"
  printf '%s/owner\n' "$lock_dir"
}

lock_age_seconds() {
  local lock_dir="$1"
  local owner_file
  owner_file=$(lock_owner_file "$lock_dir")
  if [ -f "$owner_file" ]; then
    file_age_seconds "$owner_file"
    return 0
  fi
  if [ -e "$lock_dir" ]; then
    file_age_seconds "$lock_dir"
    return 0
  fi
  echo $((stale_seconds + 1))
}

write_lock_owner() {
  local lock_dir="$1"
  local extra="${2:-}"
  write_marker "$(lock_owner_file "$lock_dir")" "$extra"
}

start_lease_keepalive() {
  local lock_dir="$1"
  local extra="${2:-}"
  stop_lease_keepalive
  (
    while true; do
      write_lock_owner "$lock_dir" "$extra"
      sleep "$heartbeat_seconds"
    done
  ) &
  lease_keepalive_pid=$!
}

stop_lease_keepalive() {
  if [ -n "${lease_keepalive_pid:-}" ] && kill -0 "$lease_keepalive_pid" 2>/dev/null; then
    kill "$lease_keepalive_pid" 2>/dev/null || true
    wait "$lease_keepalive_pid" 2>/dev/null || true
  fi
  lease_keepalive_pid=""
}

terminate_process_group() {
  local pid="${1:-}"
  local timeout_seconds="${2:-5}"
  local waited=0
  if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
    return 0
  fi

  kill -TERM -- "-${pid}" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  while kill -0 "$pid" 2>/dev/null && [ "$waited" -lt "$timeout_seconds" ]; do
    sleep 1
    waited=$((waited + 1))
  done

  if kill -0 "$pid" 2>/dev/null; then
    kill -KILL -- "-${pid}" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
  fi
}

read_pid_file_pid() {
  local path="$1"
  if [ ! -f "$path" ]; then
    return 1
  fi
  awk -F= '
    $1 == "pid" { print $2; found=1; exit }
    NR == 1 && $0 ~ /^[0-9]+$/ { print $0; found=1; exit }
    END { if (!found) exit 1 }
  ' "$path"
}

read_pid_file_host() {
  local path="$1"
  if [ ! -f "$path" ]; then
    return 1
  fi
  awk -F= '
    $1 == "host" { print $2; found=1; exit }
    END { if (!found) exit 1 }
  ' "$path"
}

write_pid_file() {
  local path="$1"
  local pid="$2"
  write_text_atomic "$path" "pid=${pid}"$'\n'"host=$(hostname)"$'\n'"role=${role}"
}

sleep_with_backoff() {
  local attempt="$1"
  local delay="$retry_backoff_seconds"
  local i
  local jitter=0
  for ((i=1; i<attempt; ++i)); do
    delay=$((delay * retry_backoff_multiplier))
    if [ "$delay" -ge "$retry_backoff_max_seconds" ]; then
      delay="$retry_backoff_max_seconds"
      break
    fi
  done
  if [ "$retry_jitter_seconds" -gt 0 ]; then
    jitter=$((RANDOM % (retry_jitter_seconds + 1)))
  fi
  log "Sleeping $((delay + jitter))s before retry"
  sleep $((delay + jitter))
}

assert_cut_manifest_readable() {
  local path="$1"
  if [ ! -f "$path" ]; then
    echo "Missing manifest: $path" >&2
    return 1
  fi
  python3 - "$path" <<'PY'
import sys
from pathlib import Path
from lhotse import CutSet

path = Path(sys.argv[1])
cuts = CutSet.from_file(path)
it = iter(cuts)
try:
    next(it)
except StopIteration:
    pass
PY
}

discover_raw_shards() {
  local raw_path
  local file_name
  local idx

  ALL_RAW_SHARD_PATHS=()
  RAW_SHARD_PATH_BY_IDX=()
  RAW_SHARD_PATH_BY_NUM=()
  while IFS= read -r raw_path; do
    ALL_RAW_SHARD_PATHS+=("$raw_path")
    file_name=$(basename "$raw_path")
    idx="${file_name#${prefix}_cuts_train_raw.}"
    idx="${idx%.jsonl.gz}"
    RAW_SHARD_PATH_BY_IDX["$idx"]="$raw_path"
    RAW_SHARD_PATH_BY_NUM["$((10#$idx))"]="$raw_path"
  done < <(
    find "$train_feature_split_dir" -maxdepth 1 -name "${prefix}_cuts_train_raw.*.jsonl.gz" | sort
  )
}

output_cuts_path_for_idx() {
  local idx="$1"
  printf '%s/%s_cuts_train.%s.jsonl.gz\n' "$train_feature_split_dir" "$prefix" "$idx"
}

output_storage_path_for_idx() {
  local idx="$1"
  printf '%s/%s_feats_train_%s\n' "$train_feature_split_dir" "$prefix" "$idx"
}

shard_output_complete() {
  local idx="$1"
  [ -f "$(output_cuts_path_for_idx "$idx")" ] && [ -f "$(output_storage_path_for_idx "$idx").lca" ]
}

cleanup_stage4_outputs() {
  local split
  for split in train dev test; do
    remove_path_if_exists \
      "${fbank_dir}/${prefix}_recordings_${split}_audio_fixed.jsonl.gz" \
      "${fbank_dir}/${prefix}_supervisions_${split}_norm.jsonl.gz" \
      "${fbank_dir}/${prefix}_supervisions_${split}_norm_fixed.jsonl.gz" \
      "${fbank_dir}/${prefix}_cuts_${split}_raw.jsonl.gz"
  done
}

cleanup_stage5_outputs() {
  local split
  for split in dev test; do
    remove_path_if_exists \
      "${fbank_dir}/${prefix}_cuts_${split}.jsonl.gz" \
      "${fbank_dir}/${prefix}_feats_${split}" \
      "${fbank_dir}/${prefix}_feats_${split}.lca"
  done
}

cleanup_stage6_outputs() {
  remove_path_if_exists "$train_feature_split_dir"
}

cleanup_stage8_outputs() {
  remove_path_if_exists \
    "${fbank_dir}/musan_feats" \
    "${fbank_dir}/musan_cuts.jsonl.gz" \
    "${fbank_dir}/.musan.done"
}

cleanup_stage9_outputs() {
  remove_path_if_exists "${fbank_dir}/${prefix}_cuts_train.jsonl.gz"
}

cleanup_stage10_outputs() {
  remove_path_if_exists "$lang_dir"
}

load_shard_ids_from_list() {
  local list_path="$1"
  local -n out_ref="$2"
  out_ref=()
  if [ ! -f "$list_path" ]; then
    return 0
  fi
  mapfile -t out_ref < <(
    sed -e 's/[[:space:]]*#.*$//' -e '/^[[:space:]]*$/d' "$list_path"
  )
}

cleanup_stage7_outputs_for_list() {
  local list_path="$1"
  local shard_ids=()
  local shard_id
  local raw_path
  local idx

  discover_raw_shards
  load_shard_ids_from_list "$list_path" shard_ids
  for shard_id in "${shard_ids[@]}"; do
    raw_path="${RAW_SHARD_PATH_BY_IDX[$shard_id]:-${RAW_SHARD_PATH_BY_NUM[$((10#$shard_id))]:-}}"
    if [ -z "$raw_path" ]; then
      continue
    fi
    idx=$(basename "$raw_path")
    idx="${idx#${prefix}_cuts_train_raw.}"
    idx="${idx%.jsonl.gz}"
    remove_path_if_exists \
      "$(output_cuts_path_for_idx "$idx")" \
      "$(output_storage_path_for_idx "$idx")" \
      "$(output_storage_path_for_idx "$idx").lca"
  done
}

verify_stage7_outputs_for_list() {
  local list_path="$1"
  local shard_ids=()
  local shard_id
  local raw_path
  local idx

  discover_raw_shards
  load_shard_ids_from_list "$list_path" shard_ids
  for shard_id in "${shard_ids[@]}"; do
    raw_path="${RAW_SHARD_PATH_BY_IDX[$shard_id]:-${RAW_SHARD_PATH_BY_NUM[$((10#$shard_id))]:-}}"
    if [ -z "$raw_path" ]; then
      echo "Missing raw shard for ${shard_id}" >&2
      return 1
    fi
    idx=$(basename "$raw_path")
    idx="${idx#${prefix}_cuts_train_raw.}"
    idx="${idx%.jsonl.gz}"
    shard_output_complete "$idx"
  done
}

start_heartbeat_loop() {
  local heartbeat_file="$1"
  local generation="$2"
  local attempt="$3"
  stop_heartbeat_loop
  (
    while true; do
      write_marker "$heartbeat_file" "generation=${generation}"$'\n'"attempt=${attempt}"$'\n'"state=running"
      sleep "$heartbeat_seconds"
    done
  ) &
  heartbeat_pid=$!
}

stop_heartbeat_loop() {
  if [ -n "${heartbeat_pid:-}" ] && kill -0 "$heartbeat_pid" 2>/dev/null; then
    kill "$heartbeat_pid" 2>/dev/null || true
    wait "$heartbeat_pid" 2>/dev/null || true
  fi
  heartbeat_pid=""
}

prepare_common_args=(
  --language "$language"
  --dataset-root "$dataset_root"
  --artifact-root "$artifact_root"
  --recording-num-splits "$recording_num_splits"
  --feature-num-splits "$feature_num_splits"
  --feature-device "$feature_device"
  --feature-num-workers "$feature_num_workers"
  --feature-batch-duration "$feature_batch_duration"
  --enable-musan "$enable_musan"
  --max-jsonl-files "$max_jsonl_files"
  --max-utterances "$max_utterances"
)

run_prepare_stage0_3() {
  bash "${SCRIPT_DIR}/run_data_pipeline.sh" "${prepare_common_args[@]}" --stage 0 --stop-stage 3
}

run_prepare_stage4() {
  bash "${SCRIPT_DIR}/run_data_pipeline.sh" "${prepare_common_args[@]}" --stage 4 --stop-stage 4
}

run_prepare_stage5() {
  bash "${SCRIPT_DIR}/run_data_pipeline.sh" "${prepare_common_args[@]}" --stage 5 --stop-stage 5
}

run_prepare_stage6() {
  bash "${SCRIPT_DIR}/run_data_pipeline.sh" "${prepare_common_args[@]}" --stage 6 --stop-stage 6
}

run_prepare_stage8() {
  bash "${SCRIPT_DIR}/run_data_pipeline.sh" "${prepare_common_args[@]}" --stage 8 --stop-stage 8
}

run_prepare_stage9() {
  bash "${SCRIPT_DIR}/run_data_pipeline.sh" "${prepare_common_args[@]}" --stage 9 --stop-stage 9
}

run_prepare_stage10() {
  bash "${SCRIPT_DIR}/run_data_pipeline.sh" "${prepare_common_args[@]}" --stage 10 --stop-stage 10
}

run_prepare_stage7_for_list() {
  local list_path="$1"
  bash "${SCRIPT_DIR}/run_data_pipeline.sh" \
    "${prepare_common_args[@]}" \
    --stage 7 \
    --stop-stage 7 \
    --feature-shard-list "$list_path"
}

verify_stage4() {
  local split
  [ -f "${fbank_dir}/${prefix}_recordings_train_audio_fixed.jsonl.gz" ]
  assert_cut_manifest_readable "${fbank_dir}/${prefix}_cuts_train_raw.jsonl.gz"

  for split in dev test; do
    if [ -f "${fbank_dir}/${prefix}_recordings_${split}_audio_fixed.jsonl.gz" ]; then
      assert_cut_manifest_readable "${fbank_dir}/${prefix}_cuts_${split}_raw.jsonl.gz"
    fi
  done
}

verify_stage5() {
  return 0
}

verify_stage6() {
  discover_raw_shards
  [ "${#ALL_RAW_SHARD_PATHS[@]}" -eq "$feature_num_splits" ]
}

verify_stage8() {
  if [ "$enable_musan" = false ]; then
    return 0
  fi
  [ -e "${fbank_dir}/.musan.done" ]
}

verify_stage9() {
  assert_cut_manifest_readable "${fbank_dir}/${prefix}_cuts_train.jsonl.gz"
}

verify_stage10() {
  [ -f "${lang_dir}/bpe.model" ]
  [ -f "${lang_dir}/tokens.txt" ]
  [ -f "${lang_dir}/L_disambig.pt" ]
}

run_stage_with_retries() {
  local label="$1"
  local cleanup_fn="$2"
  local run_fn="$3"
  local verify_fn="$4"
  local done_marker="${run_dir}/${label}.done"
  local failed_marker="${run_dir}/${label}.failed"
  local attempt_dir="${attempts_root}/${label}"
  local attempt
  local attempt_log
  local status

  if [ -f "$done_marker" ]; then
    log "${label}: already done"
    return 0
  fi

  mkdir -p "$attempt_dir"
  rm -f "$failed_marker"

  for ((attempt=1; attempt<=max_attempts; ++attempt)); do
    attempt_log="${attempt_dir}/attempt-${attempt}.log"
    log "${label}: attempt ${attempt}/${max_attempts}"
    "$cleanup_fn"
    if "$run_fn" >"$attempt_log" 2>&1; then
      if "$verify_fn" >>"$attempt_log" 2>&1; then
        write_marker "$done_marker" "attempt=${attempt}"
        log "${label}: success"
        return 0
      fi
      status=$?
    else
      status=$?
    fi

    if [ "$attempt" -eq "$max_attempts" ]; then
      write_marker "$failed_marker" "attempt=${attempt}"$'\n'"status=${status}"
      return "$status"
    fi
    log "${label}: attempt ${attempt} failed with status=${status}, see ${attempt_log}"
    sleep_with_backoff "$attempt"
  done
}

resolve_active_run_id() {
  local candidate=""
  local candidate_run_dir=""

  if [ ! -f "$current_run_id_file" ]; then
    return 1
  fi
  candidate=$(cat "$current_run_id_file")
  if [ -z "$candidate" ]; then
    return 1
  fi
  candidate_run_dir="${state_root}/runs/${candidate}"
  if [ ! -d "$candidate_run_dir" ]; then
    return 1
  fi
  if [ -f "${candidate_run_dir}/pipeline.done" ] || [ -f "${candidate_run_dir}/pipeline.failed" ]; then
    return 1
  fi
  printf '%s\n' "$candidate"
}

ensure_run_id_host() {
  mkdir -p "$state_root"
  if [ "$run_id" = auto ]; then
    if run_id=$(resolve_active_run_id); then
      :
    else
      run_id="run-$(date -u '+%Y%m%dT%H%M%SZ')-$(hostname -s)-$$"
      write_text_atomic "$current_run_id_file" "$run_id"
    fi
  else
    write_text_atomic "$current_run_id_file" "$run_id"
  fi
}

ensure_run_id_worker() {
  if [ "$run_id" != auto ]; then
    return 0
  fi
  while [ ! -f "$current_run_id_file" ]; do
    echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] waiting for ${current_run_id_file}"
    sleep "$poll_seconds"
  done
  run_id=$(cat "$current_run_id_file")
}

initialize_run_layout() {
  run_dir="${state_root}/runs/${run_id}"
  logs_root="${artifact_root}/logs/stage4_10/${run_id}"
  attempts_root="${logs_root}/attempts"
  host_lock_dir="${run_dir}/host.lock"
  stage7_dir="${run_dir}/stage7"
  stage7_generations_dir="${stage7_dir}/generations"
  stage7_assignment_lock_dir="${stage7_dir}/assignment.lock"
  stage7_current_generation_file="${stage7_dir}/current_generation"
  stage7_done_marker="${stage7_dir}/stage7.done"
  stage7_ready_marker="${stage7_dir}/stage7.ready"
  stage7_preparing_lock_dir="${stage7_dir}/host-preparing.lock"
  worker_locks_dir="${stage7_dir}/worker-locks"
  pipeline_done_marker="${run_dir}/pipeline.done"
  pipeline_failed_marker="${run_dir}/pipeline.failed"
  if [ "$role" = host ]; then
    role_log_file="${logs_root}/host.log"
    local_worker_pid_file="${logs_root}/worker.$(printf '%02d' "$local_worker_index").pid"
    local_worker_launcher_log="${logs_root}/worker.$(printf '%02d' "$local_worker_index").launcher.log"
  else
    role_log_file="${logs_root}/worker.$(printf '%02d' "$worker_index").log"
    worker_lock_dir="${worker_locks_dir}/worker-$(printf '%02d' "$worker_index").lock"
  fi

  mkdir -p "$run_dir" "$logs_root" "$attempts_root" "$stage7_generations_dir" "$worker_locks_dir"
}

cleanup_on_exit() {
  stop_heartbeat_loop
  stop_lease_keepalive
  if [ "$held_stage7_assignment_lock" = true ]; then
    rm -rf "$stage7_assignment_lock_dir"
  fi
  if [ "$held_stage7_preparing_lock" = true ]; then
    rm -rf "$stage7_preparing_lock_dir"
  fi
  if [ "$held_host_lock" = true ]; then
    rm -rf "$host_lock_dir"
  fi
  if [ "$held_worker_lock" = true ]; then
    rm -rf "$worker_lock_dir"
  fi
  if [ "$launched_local_worker" = true ] && [ -n "${local_worker_pid:-}" ]; then
    terminate_process_group "$local_worker_pid"
    wait "$local_worker_pid" 2>/dev/null || true
  fi
  if [ -n "${supervisor_child_pid:-}" ]; then
    terminate_process_group "$supervisor_child_pid"
    wait "$supervisor_child_pid" 2>/dev/null || true
  fi
}

trap cleanup_on_exit EXIT INT TERM

mark_pipeline_done() {
  write_marker "$pipeline_done_marker" "run_id=${run_id}"
}

mark_pipeline_failed() {
  local status="$1"
  write_marker "$pipeline_failed_marker" "run_id=${run_id}"$'\n'"status=${status}"
}

acquire_stage7_assignment_lock() {
  local wait_logged=false
  while true; do
    if mkdir "$stage7_assignment_lock_dir" 2>/dev/null; then
      held_stage7_assignment_lock=true
      write_marker "${stage7_assignment_lock_dir}/owner" "run_id=${run_id}"
      return 0
    fi

    if [ -d "$stage7_assignment_lock_dir" ] && [ "$(file_age_seconds "$stage7_assignment_lock_dir")" -gt "$stale_seconds" ]; then
      log "Removing stale stage7 assignment lock ${stage7_assignment_lock_dir}"
      rm -rf "$stage7_assignment_lock_dir"
      continue
    fi

    if [ "$wait_logged" = false ]; then
      log "Waiting for stage7 assignment lock ${stage7_assignment_lock_dir}"
      wait_logged=true
    fi
    sleep "$poll_seconds"
  done
}

release_stage7_assignment_lock() {
  if [ "$held_stage7_assignment_lock" = true ]; then
    rm -rf "$stage7_assignment_lock_dir"
    held_stage7_assignment_lock=false
  fi
}

acquire_stage7_preparing_lock() {
  local wait_logged=false
  if [ -f "$stage7_ready_marker" ]; then
    return 0
  fi

  while true; do
    if mkdir "$stage7_preparing_lock_dir" 2>/dev/null; then
      held_stage7_preparing_lock=true
      write_marker "${stage7_preparing_lock_dir}/owner" "run_id=${run_id}"
      return 0
    fi

    if [ -d "$stage7_preparing_lock_dir" ] && [ "$(file_age_seconds "$stage7_preparing_lock_dir")" -gt "$stale_seconds" ]; then
      log "Removing stale stage7 preparing lock ${stage7_preparing_lock_dir}"
      rm -rf "$stage7_preparing_lock_dir"
      continue
    fi

    if [ "$wait_logged" = false ]; then
      log "Waiting for stage7 preparing lock ${stage7_preparing_lock_dir}"
      wait_logged=true
    fi
    sleep "$poll_seconds"
  done
}

release_stage7_preparing_lock() {
  if [ "$held_stage7_preparing_lock" = true ]; then
    rm -rf "$stage7_preparing_lock_dir"
    held_stage7_preparing_lock=false
  fi
}

acquire_host_lock() {
  local wait_logged=false
  local owner_extra="run_id=${run_id}"

  while true; do
    if mkdir "$host_lock_dir" 2>/dev/null; then
      held_host_lock=true
      write_lock_owner "$host_lock_dir" "$owner_extra"
      start_lease_keepalive "$host_lock_dir" "$owner_extra"
      log "Acquired host lock ${host_lock_dir}"
      return 0
    fi

    if [ -d "$host_lock_dir" ] && [ "$(lock_age_seconds "$host_lock_dir")" -gt "$stale_seconds" ]; then
      log "Removing stale host lock ${host_lock_dir}"
      rm -rf "$host_lock_dir"
      continue
    fi

    if [ "$wait_logged" = false ]; then
      log "Waiting for host lock ${host_lock_dir}"
      wait_logged=true
    fi
    sleep "$poll_seconds"
  done
}

acquire_worker_lock() {
  local wait_logged=false
  local owner_extra="run_id=${run_id}"$'\n'"worker_index=${worker_index}"

  while true; do
    if [ -f "$pipeline_done_marker" ] || [ -f "$stage7_done_marker" ]; then
      return 10
    fi

    if mkdir "$worker_lock_dir" 2>/dev/null; then
      held_worker_lock=true
      write_lock_owner "$worker_lock_dir" "$owner_extra"
      start_lease_keepalive "$worker_lock_dir" "$owner_extra"
      log "Acquired worker lock ${worker_lock_dir}"
      return 0
    fi

    if [ -d "$worker_lock_dir" ] && [ "$(lock_age_seconds "$worker_lock_dir")" -gt "$stale_seconds" ]; then
      log "Removing stale worker lock ${worker_lock_dir}"
      rm -rf "$worker_lock_dir"
      continue
    fi

    if [ "$wait_logged" = false ]; then
      log "Waiting for worker lock ${worker_lock_dir}"
      wait_logged=true
    fi
    sleep "$poll_seconds"
  done
}

mark_stage7_ready() {
  if [ -f "$stage7_ready_marker" ]; then
    log "stage7.ready already exists"
    release_stage7_preparing_lock
    return 0
  fi

  write_marker "$stage7_ready_marker" "run_id=${run_id}"
  release_stage7_preparing_lock
  log "Wrote stage7 ready marker ${stage7_ready_marker}"
}

pid_is_running() {
  local pid="${1:-}"
  if [ -z "$pid" ]; then
    return 1
  fi
  kill -0 "$pid" 2>/dev/null
}

launch_local_stage7_worker() {
  local existing_pid=""
  local existing_host=""

  if [ "$launch_local_worker" != true ]; then
    return 0
  fi

  if [ "$local_worker_index" -lt 0 ] || [ "$local_worker_index" -ge "$num_stage7_workers" ]; then
    echo "$0: --local-worker-index must be in [0, ${num_stage7_workers})"
    exit 1
  fi

  if [ -f "$local_worker_pid_file" ]; then
    existing_pid=$(read_pid_file_pid "$local_worker_pid_file" 2>/dev/null || true)
    existing_host=$(read_pid_file_host "$local_worker_pid_file" 2>/dev/null || true)
    if [ "$existing_host" = "$(hostname)" ] && pid_is_running "$existing_pid"; then
      log "Reusing local stage7 worker pid=${existing_pid} index=${local_worker_index}"
      return 0
    fi
    rm -f "$local_worker_pid_file"
  fi

  mkdir -p "$(dirname "$local_worker_launcher_log")"
  : >"$local_worker_launcher_log"

  log "Launching local stage7 worker index=${local_worker_index}"
  nohup setsid bash "${SELF_PATH}" \
    --role worker \
    --supervise "$local_worker_supervise" \
    --language "$language" \
    --dataset-root "$dataset_root" \
    --artifact-root "$artifact_root" \
    --run-id "$run_id" \
    --worker-index "$local_worker_index" \
    --num-stage7-workers "$num_stage7_workers" \
    --feature-num-splits "$feature_num_splits" \
    --feature-num-workers "$feature_num_workers" \
    --feature-batch-duration "$feature_batch_duration" \
    --feature-device "$feature_device" \
    --enable-musan "$enable_musan" \
    --poll-seconds "$poll_seconds" \
    --heartbeat-seconds "$heartbeat_seconds" \
    --stale-seconds "$stale_seconds" \
    --max-attempts "$max_attempts" \
    --retry-backoff-seconds "$retry_backoff_seconds" \
    --retry-backoff-multiplier "$retry_backoff_multiplier" \
    --retry-backoff-max-seconds "$retry_backoff_max_seconds" \
    --retry-jitter-seconds "$retry_jitter_seconds" \
    >"$local_worker_launcher_log" 2>&1 &
  local_worker_pid="$!"
  launched_local_worker=true
  write_pid_file "$local_worker_pid_file" "$local_worker_pid"
  log "Local stage7 worker index=${local_worker_index} pid=${local_worker_pid}"
}

next_generation_name() {
  local generation_dir
  local next_num=1
  local current_num
  for generation_dir in "$stage7_generations_dir"/gen-*; do
    current_num="${generation_dir##*/gen-}"
    current_num=$((10#$current_num))
    if [ "$current_num" -ge "$next_num" ]; then
      next_num=$((current_num + 1))
    fi
  done
  printf 'gen-%05d\n' "$next_num"
}

collect_remaining_entries() {
  local -n out_entries="$1"
  local raw_path
  local file_name
  local idx
  local size

  out_entries=()
  discover_raw_shards
  for raw_path in "${ALL_RAW_SHARD_PATHS[@]}"; do
    file_name=$(basename "$raw_path")
    idx="${file_name#${prefix}_cuts_train_raw.}"
    idx="${idx%.jsonl.gz}"
    if shard_output_complete "$idx"; then
      continue
    fi
    size=$(stat -c '%s' "$raw_path")
    out_entries+=("${size}"$'\t'"${idx}")
  done
}

create_generation() {
  local remaining_entries=()
  local generation
  local current_generation=""
  local generation_dir
  local -a worker_loads=()
  local -a worker_lists=()
  local worker
  local entry
  local size
  local idx
  local best_worker
  local best_load
  local list_file

  created_generation_result=""
  acquire_stage7_assignment_lock
  current_generation=$(cat "$stage7_current_generation_file" 2>/dev/null || true)
  if [ -n "$current_generation" ]; then
    if ! generation_exists "$current_generation"; then
      clear_current_generation "$current_generation"
    elif generation_all_done "$current_generation"; then
      clear_current_generation "$current_generation"
    else
      created_generation_result="$current_generation"
      release_stage7_assignment_lock
      log "Reusing existing current generation ${current_generation}"
      return 0
    fi
  fi
  collect_remaining_entries remaining_entries
  if [ "${#remaining_entries[@]}" -eq 0 ]; then
    touch "$stage7_done_marker"
    release_stage7_assignment_lock
    return 0
  fi

  generation=$(next_generation_name)
  generation_dir="${stage7_generations_dir}/${generation}"
  mkdir -p "$generation_dir"

  for ((worker=0; worker<num_stage7_workers; ++worker)); do
    worker_loads[$worker]=0
    worker_lists[$worker]=""
  done

  while IFS= read -r entry; do
    IFS=$'\t' read -r size idx <<<"$entry"
    best_worker=0
    best_load=${worker_loads[0]}
    for ((worker=1; worker<num_stage7_workers; ++worker)); do
      if [ "${worker_loads[$worker]}" -lt "$best_load" ]; then
        best_worker="$worker"
        best_load=${worker_loads[$worker]}
      fi
    done
    worker_loads[$best_worker]=$((worker_loads[$best_worker] + size))
    worker_lists[$best_worker]+="${idx}"$'\n'
  done < <(printf '%s\n' "${remaining_entries[@]}" | sort -t $'\t' -k1,1nr -k2,2n)

  for ((worker=0; worker<num_stage7_workers; ++worker)); do
    list_file="${generation_dir}/worker-$(printf '%02d' "$worker").shards.txt"
    write_text_atomic "$list_file" "${worker_lists[$worker]}"
  done

  write_marker "${generation_dir}/created" "remaining_shards=${#remaining_entries[@]}"
  write_text_atomic "$stage7_current_generation_file" "$generation"
  release_stage7_assignment_lock
  log "Created ${generation} with ${#remaining_entries[@]} remaining stage7 shards"
  created_generation_result="$generation"
  return 0
}

generation_all_done() {
  local generation="$1"
  local worker
  for ((worker=0; worker<num_stage7_workers; ++worker)); do
    if [ ! -f "${stage7_generations_dir}/${generation}/worker-$(printf '%02d' "$worker").done" ]; then
      return 1
    fi
  done
  return 0
}

count_generation_done_workers() {
  local generation="$1"
  local worker
  local count=0
  for ((worker=0; worker<num_stage7_workers; ++worker)); do
    if [ -f "${stage7_generations_dir}/${generation}/worker-$(printf '%02d' "$worker").done" ]; then
      count=$((count + 1))
    fi
  done
  printf '%s\n' "$count"
}

generation_has_failed_workers() {
  local generation="$1"
  local worker
  for ((worker=0; worker<num_stage7_workers; ++worker)); do
    if [ -f "${stage7_generations_dir}/${generation}/worker-$(printf '%02d' "$worker").failed" ]; then
      return 0
    fi
  done
  return 1
}

generation_exists() {
  local generation="$1"
  [ -d "${stage7_generations_dir}/${generation}" ]
}

clear_current_generation() {
  local generation="${1:-}"
  local current_generation=""
  if [ ! -f "$stage7_current_generation_file" ]; then
    return 0
  fi

  if [ -n "$generation" ]; then
    current_generation=$(cat "$stage7_current_generation_file" 2>/dev/null || true)
    if [ "$current_generation" != "$generation" ]; then
      return 0
    fi
  fi

  rm -f "$stage7_current_generation_file"
}

mark_stage7_done() {
  local extra="${1:-}"
  clear_current_generation
  write_marker "$stage7_done_marker" "$extra"
}

generation_has_fresh_activity() {
  local generation="$1"
  local worker
  local heartbeat_file
  for ((worker=0; worker<num_stage7_workers; ++worker)); do
    if [ -f "${stage7_generations_dir}/${generation}/worker-$(printf '%02d' "$worker").done" ]; then
      continue
    fi
    heartbeat_file="${stage7_generations_dir}/${generation}/worker-$(printf '%02d' "$worker").heartbeat"
    if [ -f "$heartbeat_file" ] && [ "$(file_age_seconds "$heartbeat_file")" -le "$stale_seconds" ]; then
      return 0
    fi
  done
  return 1
}

generation_has_stale_workers() {
  local generation="$1"
  local created="${stage7_generations_dir}/${generation}/created"
  local worker
  local heartbeat_file

  if [ ! -f "$created" ] || [ "$(file_age_seconds "$created")" -le "$stale_seconds" ]; then
    return 1
  fi

  for ((worker=0; worker<num_stage7_workers; ++worker)); do
    if [ -f "${stage7_generations_dir}/${generation}/worker-$(printf '%02d' "$worker").done" ]; then
      continue
    fi
    if [ -f "${stage7_generations_dir}/${generation}/worker-$(printf '%02d' "$worker").failed" ]; then
      continue
    fi
    heartbeat_file="${stage7_generations_dir}/${generation}/worker-$(printf '%02d' "$worker").heartbeat"
    if [ ! -f "$heartbeat_file" ] || [ "$(file_age_seconds "$heartbeat_file")" -gt "$stale_seconds" ]; then
      return 0
    fi
  done
  return 1
}

wait_for_generation_terminal() {
  local generation="$1"
  local done_count=0
  while true; do
    if generation_all_done "$generation"; then
      log "${generation}: all workers done"
      return 0
    fi
    if generation_has_failed_workers "$generation"; then
      log "${generation}: found failed worker marker"
      return 1
    fi
    if generation_has_stale_workers "$generation"; then
      log "${generation}: found stale worker"
      return 1
    fi
    done_count=$(count_generation_done_workers "$generation")
    log "${generation}: progress ${done_count}/${num_stage7_workers} workers done; sleeping ${poll_seconds}s"
    sleep "$poll_seconds"
  done
}

run_host_stage7() {
  local generation=""
  local remaining_entries=()
  local wait_status=0

  if [ -f "$stage7_done_marker" ]; then
    log "stage7: already done"
    return 0
  fi

  while true; do
    collect_remaining_entries remaining_entries
    if [ "${#remaining_entries[@]}" -eq 0 ]; then
      mark_stage7_done "reason=no_remaining_shards"
      log "stage7: no remaining shards"
      return 0
    fi

    generation=$(cat "$stage7_current_generation_file" 2>/dev/null || true)
    if [ -n "$generation" ]; then
      if ! generation_exists "$generation"; then
        log "stage7: current generation ${generation} is missing; clearing stale pointer"
        clear_current_generation "$generation"
      elif generation_all_done "$generation"; then
        log "stage7: current generation ${generation} already finished"
        clear_current_generation "$generation"
      elif generation_has_fresh_activity "$generation" || ! generation_has_stale_workers "$generation"; then
        log "stage7: attaching to current generation ${generation}"
        if wait_for_generation_terminal "$generation"; then
          wait_status=0
        else
          wait_status=$?
        fi
        if [ "$wait_status" -eq 0 ]; then
          clear_current_generation "$generation"
          log "stage7: generation ${generation} reached terminal success state"
        else
          clear_current_generation "$generation"
          log "stage7: generation ${generation} reached terminal failure state; rescanning remaining shards"
        fi
      else
        log "stage7: generation ${generation} has no fresh activity, reallocating remaining shards"
        clear_current_generation "$generation"
      fi
      collect_remaining_entries remaining_entries
      if [ "${#remaining_entries[@]}" -eq 0 ]; then
        mark_stage7_done "reason=all_shards_completed"$'\n'"generation=${generation}"
        log "stage7: all shards are done after generation ${generation}"
        return 0
      fi
    fi

    create_generation
    generation="$created_generation_result"
    if [ -z "$generation" ]; then
      mark_stage7_done "reason=allocator_found_no_remaining_shards"
      log "stage7: nothing left after allocation scan"
      return 0
    fi
    if wait_for_generation_terminal "$generation"; then
      wait_status=0
    else
      wait_status=$?
    fi
    if [ "$wait_status" -eq 0 ]; then
      clear_current_generation "$generation"
      log "stage7: generation ${generation} completed; rescanning for any remaining shards"
    else
      clear_current_generation "$generation"
      log "stage7: generation ${generation} failed or went stale; reallocating unfinished shards"
    fi
  done
}

pre_stage_failed() {
  local label
  if [ -f "$pipeline_failed_marker" ]; then
    log "worker ${worker_index}: pipeline.failed exists, aborting stage7 wait"
    return 0
  fi
  for label in stage0_3 stage4 stage5 stage6; do
    if [ -f "${run_dir}/${label}.failed" ]; then
      log "worker ${worker_index}: ${label}.failed exists, aborting stage7 wait"
      return 0
    fi
  done
  return 1
}

wait_for_stage7_ready() {
  while true; do
    if [ -f "$pipeline_done_marker" ] || [ -f "$stage7_done_marker" ]; then
      return 0
    fi
    if pre_stage_failed; then
      return 1
    fi
    if [ -f "$stage7_ready_marker" ] && [ ! -d "$stage7_preparing_lock_dir" ]; then
      log "worker ${worker_index}: observed stage7 ready marker"
      return 0
    fi
    log "worker ${worker_index}: waiting for ${stage7_ready_marker}"
    sleep "$poll_seconds"
  done
}

wait_for_stage7_generation_ready() {
  while true; do
    if [ -f "$pipeline_done_marker" ] || [ -f "$stage7_done_marker" ]; then
      echo ""
      return 0
    fi
    if [ -f "$stage7_current_generation_file" ]; then
      cat "$stage7_current_generation_file"
      return 0
    fi
    sleep "$poll_seconds"
  done
}

run_generation_with_retries() {
  local generation="$1"
  local list_path="$2"
  local done_marker="${stage7_generations_dir}/${generation}/worker-$(printf '%02d' "$worker_index").done"
  local failed_marker="${stage7_generations_dir}/${generation}/worker-$(printf '%02d' "$worker_index").failed"
  local heartbeat_file="${stage7_generations_dir}/${generation}/worker-$(printf '%02d' "$worker_index").heartbeat"
  local attempt_dir="${attempts_root}/stage7/worker-${worker_index}/gen-${generation}"
  local attempt
  local attempt_log
  local status

  if [ -f "$done_marker" ]; then
    log "stage7 ${generation}: worker ${worker_index} already done"
    return 0
  fi

  mkdir -p "$attempt_dir"
  rm -f "$failed_marker"

  for ((attempt=1; attempt<=max_attempts; ++attempt)); do
    attempt_log="${attempt_dir}/attempt-${attempt}.log"
    cleanup_stage7_outputs_for_list "$list_path"
    start_heartbeat_loop "$heartbeat_file" "$generation" "$attempt"
    log "stage7 ${generation}: worker ${worker_index} attempt ${attempt}/${max_attempts}"
    if run_prepare_stage7_for_list "$list_path" >"$attempt_log" 2>&1 && verify_stage7_outputs_for_list "$list_path" >>"$attempt_log" 2>&1; then
      stop_heartbeat_loop
      write_marker "$heartbeat_file" "generation=${generation}"$'\n'"attempt=${attempt}"$'\n'"state=done"
      write_marker "$done_marker" "attempt=${attempt}"
      log "stage7 ${generation}: worker ${worker_index} success"
      return 0
    fi

    status=$?
    stop_heartbeat_loop
    log "stage7 ${generation}: worker ${worker_index} attempt ${attempt} failed with status=${status}, see ${attempt_log}"
    if [ "$attempt" -eq "$max_attempts" ]; then
      write_marker "$heartbeat_file" "generation=${generation}"$'\n'"attempt=${attempt}"$'\n'"state=failed"
      write_marker "$failed_marker" "attempt=${attempt}"$'\n'"status=${status}"
      return "$status"
    fi
    write_marker "$heartbeat_file" "generation=${generation}"$'\n'"attempt=${attempt}"$'\n'"state=backoff"
    sleep_with_backoff "$attempt"
  done
}

main_host() {
  if [ -f "$pipeline_done_marker" ]; then
    log "pipeline already done"
    return 0
  fi

  if [ -f "$pipeline_failed_marker" ]; then
    log "pipeline already marked failed"
    return 1
  fi

  acquire_host_lock
  if [ -f "$pipeline_done_marker" ]; then
    log "pipeline already done after acquiring host lock"
    return 0
  fi
  if [ -f "$pipeline_failed_marker" ]; then
    log "pipeline already marked failed after acquiring host lock"
    return 1
  fi
  acquire_stage7_preparing_lock
  launch_local_stage7_worker

  log "role=host run_id=${run_id}"
  log "dataset_root=${dataset_root}"
  log "artifact_root=${artifact_root}"
  log "recording_num_splits=${recording_num_splits}"
  log "feature_num_splits=${feature_num_splits}"
  log "num_stage7_workers=${num_stage7_workers}"
  log "feature_num_workers=${feature_num_workers}"
  log "launch_local_worker=${launch_local_worker}"
  log "local_worker_index=${local_worker_index}"
  log "local_worker_supervise=${local_worker_supervise}"
  log "max_jsonl_files=${max_jsonl_files}"
  log "max_utterances=${max_utterances}"

  run_stage_with_retries stage0_3 : run_prepare_stage0_3 true
  run_stage_with_retries stage4 cleanup_stage4_outputs run_prepare_stage4 verify_stage4
  run_stage_with_retries stage5 cleanup_stage5_outputs run_prepare_stage5 verify_stage5
  run_stage_with_retries stage6 cleanup_stage6_outputs run_prepare_stage6 verify_stage6
  mark_stage7_ready
  run_host_stage7
  run_stage_with_retries stage8 cleanup_stage8_outputs run_prepare_stage8 verify_stage8
  run_stage_with_retries stage9 cleanup_stage9_outputs run_prepare_stage9 verify_stage9
  if [ "$run_stage10" = true ]; then
    run_stage_with_retries stage10 cleanup_stage10_outputs run_prepare_stage10 verify_stage10
  fi

  mark_pipeline_done
}

main_worker() {
  local acquire_status=0

  log "role=worker run_id=${run_id} worker_index=${worker_index}"

  if [ -f "$pipeline_done_marker" ] || [ -f "$stage7_done_marker" ]; then
    log "worker ${worker_index}: pipeline/stage7 is already complete"
    return 0
  fi

  if acquire_worker_lock; then
    :
  else
    acquire_status=$?
    if [ "$acquire_status" -eq 10 ]; then
      log "worker ${worker_index}: stage7 completed while waiting for worker lock"
      return 0
    fi
    return "$acquire_status"
  fi

  wait_for_stage7_ready

  while true; do
    local generation=""
    local list_file=""
    local shard_ids=()

    if [ -f "$pipeline_done_marker" ] || [ -f "$stage7_done_marker" ]; then
      log "worker ${worker_index}: stage7 is complete"
      return 0
    fi

    generation=$(wait_for_stage7_generation_ready)
    if [ -z "$generation" ]; then
      log "worker ${worker_index}: stage7 is complete"
      return 0
    fi

    list_file="${stage7_generations_dir}/${generation}/worker-$(printf '%02d' "$worker_index").shards.txt"
    if [ ! -f "$list_file" ]; then
      log "worker ${worker_index}: waiting for shard list in ${generation}"
      sleep "$poll_seconds"
      continue
    fi

    if [ -f "${stage7_generations_dir}/${generation}/worker-$(printf '%02d' "$worker_index").done" ]; then
      sleep "$poll_seconds"
      continue
    fi

    load_shard_ids_from_list "$list_file" shard_ids
    if [ "${#shard_ids[@]}" -eq 0 ]; then
      write_marker "${stage7_generations_dir}/${generation}/worker-$(printf '%02d' "$worker_index").done" "attempt=0"$'\n'"empty_assignment=true"
      log "worker ${worker_index}: ${generation} has empty shard list"
      sleep "$poll_seconds"
      continue
    fi

    run_generation_with_retries "$generation" "$list_file"
  done
}

build_supervisor_command() {
  local -n out_ref="$1"
  out_ref=(
    bash "$SELF_PATH"
    --role "$role"
    --supervise false
    --language "$language"
    --public-root "$public_root"
    --dataset-root "$dataset_root"
    --artifact-root "$artifact_root"
    --run-id "$run_id"
    --recording-num-splits "$recording_num_splits"
    --feature-num-splits "$feature_num_splits"
    --num-stage7-workers "$num_stage7_workers"
    --feature-num-workers "$feature_num_workers"
    --feature-batch-duration "$feature_batch_duration"
    --feature-device "$feature_device"
    --enable-musan "$enable_musan"
    --poll-seconds "$poll_seconds"
    --heartbeat-seconds "$heartbeat_seconds"
    --stale-seconds "$stale_seconds"
    --max-attempts "$max_attempts"
    --retry-backoff-seconds "$retry_backoff_seconds"
    --retry-backoff-multiplier "$retry_backoff_multiplier"
    --retry-backoff-max-seconds "$retry_backoff_max_seconds"
    --retry-jitter-seconds "$retry_jitter_seconds"
  )
  if [ "$role" = host ]; then
    out_ref+=(
      --run-stage10 "$run_stage10"
      --launch-local-worker "$launch_local_worker"
      --local-worker-index "$local_worker_index"
      --local-worker-supervise "$local_worker_supervise"
      --max-jsonl-files "$max_jsonl_files"
      --max-utterances "$max_utterances"
    )
  else
    out_ref+=(--worker-index "$worker_index")
  fi
}

supervisor_terminal_status() {
  local effective_run_id=""
  local effective_run_dir=""

  if [ "$run_id" = auto ]; then
    if [ ! -f "$current_run_id_file" ]; then
      return 1
    fi
    effective_run_id=$(cat "$current_run_id_file")
  else
    effective_run_id="$run_id"
  fi

  if [ -z "$effective_run_id" ]; then
    return 1
  fi

  effective_run_dir="${state_root}/runs/${effective_run_id}"
  if [ -f "${effective_run_dir}/pipeline.done" ]; then
    return 10
  fi
  if [ -f "${effective_run_dir}/pipeline.failed" ]; then
    return 11
  fi
  if [ "$role" = worker ] && [ -f "${effective_run_dir}/stage7/stage7.done" ]; then
    return 10
  fi
  return 1
}

run_with_supervisor() {
  local restart_count=0
  local cmd=()
  local status

  while true; do
    build_supervisor_command cmd
    log "Supervisor launching role=${role} run_id=${run_id}"
    setsid "${cmd[@]}" &
    supervisor_child_pid=$!
    if wait "$supervisor_child_pid"; then
      supervisor_child_pid=""
      return 0
    fi
    status=$?
    supervisor_child_pid=""

    if supervisor_terminal_status; then
      :
    else
      status=$?
      if [ "$status" -eq 10 ]; then
        log "Supervisor observed terminal success marker for role=${role}"
        return 0
      fi
      if [ "$status" -eq 11 ]; then
        log "Supervisor observed terminal failure marker for role=${role}"
        return 1
      fi
    fi

    restart_count=$((restart_count + 1))
    if [ "$supervisor_max_restarts" -ge 0 ] && [ "$restart_count" -gt "$supervisor_max_restarts" ]; then
      log "Supervisor reached max restarts (${supervisor_max_restarts}) for role=${role}"
      return 1
    fi
    log "Supervisor restarting role=${role} after status=${status}, restart_count=${restart_count}"
    sleep_with_backoff "$restart_count"
  done
}

run_once() {
  if [ "$role" = host ]; then
    ensure_run_id_host
  else
    ensure_run_id_worker
  fi
  initialize_run_layout

  if [ "$role" = host ]; then
    if main_host; then
      return 0
    fi
    local status=$?
    if [ ! -f "$pipeline_done_marker" ] && [ ! -f "$pipeline_failed_marker" ]; then
      mark_pipeline_failed "$status"
    fi
    return "$status"
  fi

  main_worker
}

main() {
  if [ "$supervise" = true ]; then
    run_with_supervisor
  else
    run_once
  fi
}

main "$@"
