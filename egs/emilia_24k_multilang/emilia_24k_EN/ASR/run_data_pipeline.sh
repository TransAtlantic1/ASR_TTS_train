#!/usr/bin/env bash

export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ICEFALL_ROOT=$(cd -- "${SCRIPT_DIR}/../../../.." && pwd)
PARSE_OPTIONS_SH="${ICEFALL_ROOT}/icefall/shared/parse_options.sh"

stage=0
stop_stage=10

language=zh
public_root="/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public"
default_dataset_root="/inspire/dataset/emilia/fc71e07"

download_root=""
dataset_root=""
audio_cache_root=""
data_root=""
artifact_root=""

dev_ratio=0.0
test_ratio=0.0

recording_num_splits=1000
resample_start=0
resample_stop=-1
resample_num_workers=32

# Backward-compatible feature split options.
num_splits=1000
start=0
stop=-1
num_workers=24
batch_duration=2000

feature_num_splits=""
feature_start=""
feature_stop=""
feature_shard_list=""
feature_num_workers=""
feature_batch_duration=""
feature_device="auto"
stage4_probe_workers=""
stage4_probe_chunksize=64

target_sample_rate=24000
use_resampled_audio=false
# Offline stage-3 resampling is deprecated in this recipe. Features are
# extracted from source audio and resampled to 24 kHz online in the extractor.
speed_perturb=false
enable_musan=false

max_jsonl_files=-1
max_utterances=-1

. "${PARSE_OPTIONS_SH}" || exit 1

if [ -z "$feature_num_splits" ]; then
  feature_num_splits=$num_splits
fi
if [ -z "$feature_start" ]; then
  feature_start=$start
fi
if [ -z "$feature_stop" ]; then
  feature_stop=$stop
fi
if [ -z "$feature_num_workers" ]; then
  feature_num_workers=$num_workers
fi
if [ -z "$feature_batch_duration" ]; then
  feature_batch_duration=$batch_duration
fi
if [ -z "$stage4_probe_workers" ]; then
  stage4_probe_workers=$feature_num_workers
fi
if [ -z "$stage4_probe_workers" ] || [ "$stage4_probe_workers" -le 0 ]; then
  stage4_probe_workers=32
fi
if [ "$stage4_probe_chunksize" -le 0 ]; then
  stage4_probe_chunksize=64
fi

log() {
  local fname=${BASH_SOURCE[1]##*/}
  echo -e "$(date '+%Y-%m-%d %H:%M:%S') (${fname}:${BASH_LINENO[0]}:${FUNCNAME[1]}) $*"
}

if [[ "$language" != "zh" && "$language" != "en" ]]; then
  echo "$0: --language must be one of zh or en, got: $language"
  exit 1
fi

if [ -z "$artifact_root" ]; then
  artifact_root="${public_root%/}/emilia/fc71e07/icefall_emilia_${language}_24k"
fi
if [ -z "$download_root" ]; then
  download_root="${artifact_root}/download"
fi
if [ -z "$dataset_root" ]; then
  dataset_root="${default_dataset_root}"
fi
if [ -z "$audio_cache_root" ]; then
  audio_cache_root="${artifact_root}/audio_cache"
fi
if [ -z "$data_root" ]; then
  data_root="${artifact_root}/data"
fi

prefix="emilia_${language}"
manifests_root="${data_root}/manifests"
manifest_dir="${manifests_root}/${language}"
resampled_manifest_dir="${data_root}/manifests_resampled/${language}/${target_sample_rate}"
fbank_dir="${data_root}/fbank/${language}"
recording_split_dir="${manifest_dir}/recordings_train_split_${recording_num_splits}"
resampled_recording_split_dir="${resampled_manifest_dir}/recordings_train_split_${recording_num_splits}"
resample_lock_dir="${artifact_root}/locks/resample/${language}/${target_sample_rate}/recordings_train_split_${recording_num_splits}"
train_feature_split_dir="${fbank_dir}/train_split_${feature_num_splits}"
cache_dir="${audio_cache_root}/emilia/${language}"

if [[ "$language" == "zh" ]]; then
  vocab_size=2000
  lang_dir="${data_root}/lang_bpe_zh_${vocab_size}"
  transcript_file="${lang_dir}/transcript_chars.txt"
else
  vocab_size=500
  lang_dir="${data_root}/lang_bpe_en_${vocab_size}"
  transcript_file="${lang_dir}/transcript_words.txt"
fi

mkdir -p "$data_root" "$manifest_dir" "$fbank_dir" "$resampled_manifest_dir"
prepare_lang_bpe_py="${ICEFALL_ROOT}/egs/librispeech/ASR/local/prepare_lang_bpe.py"
validate_bpe_lexicon_py="${ICEFALL_ROOT}/egs/librispeech/ASR/local/validate_bpe_lexicon.py"
shared_helper_pythonpath="${ICEFALL_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

log "language: $language"
log "artifact_root: $artifact_root"
log "data_root: $data_root"
log "download_root: $download_root"
log "dataset_root: $dataset_root"
log "audio_cache_root: $audio_cache_root"
log "target_sample_rate: $target_sample_rate"
log "stage4_probe_workers: $stage4_probe_workers"

if [ $stage -le 0 ] && [ $stop_stage -ge 0 ]; then
  log "Stage 0: Prepare Emilia ${language} manifests"
  log "Stage 0: Emilia recipe-local dev/test splits are disabled; all Emilia utterances stay in train"
  python3 "${SCRIPT_DIR}/local/prepare_emilia_manifests.py" \
    --dataset-root "$dataset_root" \
    --language "$language" \
    --output-dir "$manifest_dir" \
    --dev-ratio "$dev_ratio" \
    --test-ratio "$test_ratio" \
    --max-jsonl-files "$max_jsonl_files" \
    --max-utterances "$max_utterances"
fi

if [ $stage -le 1 ] && [ $stop_stage -ge 1 ]; then
  log "Stage 1: Split train recordings into ${recording_num_splits} shards"
  if [ ! -f "${recording_split_dir}/.split_completed" ]; then
    mkdir -p "$recording_split_dir"
    lhotse split \
      "$recording_num_splits" \
      "${manifest_dir}/${prefix}_recordings_train.jsonl.gz" \
      "$recording_split_dir"
    touch "${recording_split_dir}/.split_completed"
  fi
fi

if [ $stage -le 2 ] && [ $stop_stage -ge 2 ]; then
  if [ "$enable_musan" = false ]; then
    log "Stage 2: Skipping MUSAN manifest prep because enable_musan=false"
  elif [ -e "${SCRIPT_DIR}/../../librispeech/ASR/data/fbank/.musan.done" ]; then
    log "Stage 2: Shared Librispeech MUSAN features are available; no local MUSAN manifest prep needed"
  else
    log "Stage 2: Prepare MUSAN manifests"
    musan_source_dir="${download_root}/musan"
    if [ ! -d "$musan_source_dir" ] && [ -d "${dataset_root%/}/../musan" ]; then
      musan_source_dir="${dataset_root%/}/../musan"
    fi
    if [ ! -d "$musan_source_dir" ]; then
      log "Downloading MUSAN"
      lhotse download musan "$download_root"
      musan_source_dir="${download_root}/musan"
    fi
    if [ ! -f "${manifests_root}/.musan.done" ]; then
      lhotse prepare musan "$musan_source_dir" "$manifests_root"
      touch "${manifests_root}/.musan.done"
    fi
  fi
fi

if [ $stage -le 3 ] && [ $stop_stage -ge 3 ]; then
  log "Stage 3: Offline resampling is disabled in the Emilia EN CPU cluster flow"
  log "Stage 3: Downstream stages consume original audio and rely on extractor-side online resampling to ${target_sample_rate} Hz"
  if [ "$use_resampled_audio" = true ]; then
    log "Stage 3: Ignoring deprecated --use-resampled-audio=true"
  fi
fi

if [ $stage -le 4 ] && [ $stop_stage -ge 4 ]; then
  log "Stage 4: Normalize transcripts and build raw cuts"
  speed_perturb_flag=()
  if [ "$speed_perturb" = true ]; then
    speed_perturb_flag+=(--speed-perturb)
  fi

  python3 "${SCRIPT_DIR}/local/prepare_emilia_raw_cuts.py" \
    --language "$language" \
    --manifest-dir "$manifest_dir" \
    --output-dir "$fbank_dir" \
    --recording-probe-workers "$stage4_probe_workers" \
    --recording-probe-chunksize "$stage4_probe_chunksize" \
    "${speed_perturb_flag[@]}"
fi

if [ $stage -le 5 ] && [ $stop_stage -ge 5 ]; then
  log "Stage 5: Emilia recipe-local dev/test feature extraction is disabled"
  log "Stage 5: Use external eval/dev cuts with precomputed features for validation and decoding"
fi

if [ $stage -le 6 ] && [ $stop_stage -ge 6 ]; then
  log "Stage 6: Split train raw cuts into ${feature_num_splits} shards"
  if [ ! -f "${train_feature_split_dir}/.split_completed" ]; then
    mkdir -p "$train_feature_split_dir"
    lhotse split \
      "$feature_num_splits" \
      "${fbank_dir}/${prefix}_cuts_train_raw.jsonl.gz" \
      "$train_feature_split_dir"
    touch "${train_feature_split_dir}/.split_completed"
  fi
fi

if [ $stage -le 7 ] && [ $stop_stage -ge 7 ]; then
  log "Stage 7: Compute features for train splits"
  if [ ! -d "$train_feature_split_dir" ]; then
    echo "$0: Missing split dir ${train_feature_split_dir}. Run stage 6 first."
    exit 1
  fi

  bad_cut_report_dir="${artifact_root}/orchestration/stage4_10/${language}/bad-cuts"
  mkdir -p "$bad_cut_report_dir"

  mapfile -t raw_paths < <(
    find "$train_feature_split_dir" -maxdepth 1 -name "${prefix}_cuts_train_raw.*.jsonl.gz" | sort
  )
  if [ ${#raw_paths[@]} -eq 0 ]; then
    echo "$0: No split manifests found in ${train_feature_split_dir}"
    exit 1
  fi

  selected_raw_paths=()
  if [ -n "$feature_shard_list" ]; then
    if [ ! -f "$feature_shard_list" ]; then
      echo "$0: Missing feature shard list ${feature_shard_list}"
      exit 1
    fi

    declare -A raw_path_by_idx=()
    declare -A raw_path_by_num=()
    for raw_path in "${raw_paths[@]}"; do
      file_name=$(basename "$raw_path")
      idx="${file_name#${prefix}_cuts_train_raw.}"
      idx="${idx%.jsonl.gz}"
      raw_path_by_idx["$idx"]="$raw_path"
      raw_path_by_num["$((10#$idx))"]="$raw_path"
    done

    mapfile -t requested_shards < <(
      sed -e 's/[[:space:]]*#.*$//' -e '/^[[:space:]]*$/d' "$feature_shard_list"
    )
    if [ ${#requested_shards[@]} -eq 0 ]; then
      log "Stage 7: feature_shard_list=${feature_shard_list} is empty, nothing to do"
    else
      declare -A seen_requested_shards=()
      for shard_id in "${requested_shards[@]}"; do
        if [[ ! "$shard_id" =~ ^[0-9]+$ ]]; then
          echo "$0: Invalid shard id '${shard_id}' in ${feature_shard_list}"
          exit 1
        fi

        normalized_shard_id=$(printf '%d' "$((10#$shard_id))")
        if [ -n "${seen_requested_shards[$normalized_shard_id]+x}" ]; then
          continue
        fi
        seen_requested_shards["$normalized_shard_id"]=1

        raw_path="${raw_path_by_idx[$shard_id]:-${raw_path_by_num[$normalized_shard_id]:-}}"
        if [ -z "$raw_path" ]; then
          echo "$0: Shard ${shard_id} from ${feature_shard_list} does not exist in ${train_feature_split_dir}"
          exit 1
        fi
        selected_raw_paths+=("$raw_path")
      done
    fi
  else
    total_feature_splits=${#raw_paths[@]}
    if [ "$feature_stop" -lt "$feature_start" ]; then
      feature_stop="$total_feature_splits"
    fi
    if [ "$feature_stop" -gt "$total_feature_splits" ]; then
      feature_stop="$total_feature_splits"
    fi

    for ((i=feature_start; i<feature_stop; ++i)); do
      selected_raw_paths+=("${raw_paths[$i]}")
    done
  fi

  for raw_path in "${selected_raw_paths[@]}"; do
    file_name=$(basename "$raw_path")
    idx="${file_name#${prefix}_cuts_train_raw.}"
    idx="${idx%.jsonl.gz}"
    out_path="${train_feature_split_dir}/${prefix}_cuts_train.${idx}.jsonl.gz"
    storage_path="${train_feature_split_dir}/${prefix}_feats_train_${idx}"
    python3 "${SCRIPT_DIR}/local/compute_emilia_features.py" \
      --raw-cuts-path "$raw_path" \
      --output-cuts-path "$out_path" \
      --storage-path "$storage_path" \
      --num-workers "$feature_num_workers" \
      --batch-duration "$feature_batch_duration" \
      --skip-missing-cuts true \
      --bad-cut-report-dir "$bad_cut_report_dir" \
      --device "$feature_device"
  done
fi

if [ $stage -le 8 ] && [ $stop_stage -ge 8 ]; then
  if [ "$enable_musan" = false ]; then
    log "Stage 8: Skipping MUSAN features because enable_musan=false"
  elif [ -e "${SCRIPT_DIR}/../../librispeech/ASR/data/fbank/.musan.done" ]; then
    log "Stage 8: Link shared Librispeech MUSAN features"
    mkdir -p "$fbank_dir"
    ln -snf \
      "$(realpath "${SCRIPT_DIR}/../../librispeech/ASR/data/fbank/musan_feats")" \
      "${fbank_dir}/musan_feats"
    ln -snf \
      "$(realpath "${SCRIPT_DIR}/../../librispeech/ASR/data/fbank/musan_cuts.jsonl.gz")" \
      "${fbank_dir}/musan_cuts.jsonl.gz"
    touch "${fbank_dir}/.musan.done"
  else
    log "Stage 8: Compute MUSAN features"
    if [ ! -f "${manifests_root}/.musan.done" ]; then
      echo "$0: Missing MUSAN manifests. Run stage 2 with --enable-musan true first."
      exit 1
    fi
    python3 "${SCRIPT_DIR}/local/compute_fbank_musan.py" \
      --manifest-dir "${manifests_root}" \
      --output-dir "$fbank_dir"
    touch "${fbank_dir}/.musan.done"
  fi
fi

if [ $stage -le 9 ] && [ $stop_stage -ge 9 ]; then
  log "Stage 9: Combine train split cut manifests"
  if [ ! -f "${fbank_dir}/${prefix}_cuts_train.jsonl.gz" ]; then
    pieces=$(find "$train_feature_split_dir" -name "${prefix}_cuts_train.[0-9]*.jsonl.gz" | sort)
    if [ -z "$pieces" ]; then
      echo "$0: No processed split manifests found in ${train_feature_split_dir}"
      exit 1
    fi
    lhotse combine $pieces "${fbank_dir}/${prefix}_cuts_train.jsonl.gz"
  fi
fi

if [ $stage -le 10 ] && [ $stop_stage -ge 10 ]; then
  log "Stage 10: Prepare BPE based language dir"
  mkdir -p "$lang_dir"

  cuts_source="${fbank_dir}/${prefix}_cuts_train.jsonl.gz"
  if [ ! -f "$cuts_source" ]; then
    cuts_source="$fbank_dir"
  fi

  python3 "${SCRIPT_DIR}/local/prepare_emilia_bpe_data.py" \
    --cuts-path "$cuts_source" \
    --language "$language" \
    --lang-dir "$lang_dir"

  if [ ! -f "${lang_dir}/bpe.model" ]; then
    python3 "${SCRIPT_DIR}/local/train_bpe_model.py" \
      --lang-dir "$lang_dir" \
      --transcript "$transcript_file" \
      --vocab-size "$vocab_size"
  fi

  if [ ! -f "${lang_dir}/tokens.txt" ]; then
    python3 "${SCRIPT_DIR}/local/bpe_model_to_tokens.py" "${lang_dir}/bpe.model" > "${lang_dir}/tokens.txt"
  fi

  if [ ! -f "${lang_dir}/L_disambig.pt" ]; then
    if [ ! -f "$prepare_lang_bpe_py" ]; then
      echo "$0: Missing shared helper ${prepare_lang_bpe_py}"
      exit 1
    fi
    if [ ! -f "$validate_bpe_lexicon_py" ]; then
      echo "$0: Missing shared helper ${validate_bpe_lexicon_py}"
      exit 1
    fi
    PYTHONPATH="$shared_helper_pythonpath" python3 "$prepare_lang_bpe_py" --lang-dir "$lang_dir"
    PYTHONPATH="$shared_helper_pythonpath" python3 "$validate_bpe_lexicon_py" \
      --lexicon "${lang_dir}/lexicon.txt" \
      --bpe-model "${lang_dir}/bpe.model"
  fi
fi

log "run_data_pipeline.sh: DONE"
