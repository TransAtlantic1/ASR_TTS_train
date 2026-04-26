#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_SCRIPT="${SCRIPT_DIR}/run_data_pipeline.sh"

echo "prepare_data.sh is a compatibility wrapper for the emilia_24k main pipeline."
echo "Forwarding all arguments to ${TARGET_SCRIPT}"

exec bash "${TARGET_SCRIPT}" "$@"
