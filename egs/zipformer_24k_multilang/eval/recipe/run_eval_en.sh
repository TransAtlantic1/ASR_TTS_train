#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ICEFALL_ROOT=$(cd -- "${SCRIPT_DIR}/../../../.." && pwd)
PARSE_OPTIONS_SH="${ICEFALL_ROOT}/icefall/shared/parse_options.sh"

bench_root="/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/public/eval"
results_root="${SCRIPT_DIR}/../results"
mode="once"
test_sets=""
test_set_preset="en-open-v1"
ref_modes="raw,normalized"
exp_dir=""
artifact_root=""
manifest_dir=""
lang_dir=""
bpe_model=""
avg=3
beam_size=4
decoding_methods="greedy_search,modified_beam_search"
decode_every_n=5000
poll_seconds=120
decode_max_duration=1000
decode_num_workers=0
decode_cuda_visible_devices=""
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

python3 "${SCRIPT_DIR}/../utils/run_eval.py" \
  --language en \
  --mode "${mode}" \
  --bench-root "${bench_root}" \
  --results-root "${results_root}" \
  --test-sets "${test_sets}" \
  --test-set-preset "${test_set_preset}" \
  --ref-modes "${ref_modes}" \
  --exp-dir "${exp_dir}" \
  --artifact-root "${artifact_root}" \
  --manifest-dir "${manifest_dir}" \
  --lang-dir "${lang_dir}" \
  --bpe-model "${bpe_model}" \
  --avg "${avg}" \
  --beam-size "${beam_size}" \
  --decoding-methods "${decoding_methods}" \
  --decode-every-n "${decode_every_n}" \
  --poll-seconds "${poll_seconds}" \
  --decode-max-duration "${decode_max_duration}" \
  --decode-num-workers "${decode_num_workers}" \
  --decode-cuda-visible-devices "${decode_cuda_visible_devices}" \
  --use-averaged-model "${use_averaged_model}" \
  --start-iter "${start_iter}" \
  --iter "${iter}" \
  --epoch "${epoch}" \
  --state-dir "${state_dir}" \
  --log-path "${log_path}" \
  --train-done-marker "${train_done_marker}" \
  --once "${once}" \
  --dry-run "${dry_run}" \
  --auto-resolve-run-dir "${auto_resolve_run_dir}" \
  --skip-unavailable "${skip_unavailable}"
