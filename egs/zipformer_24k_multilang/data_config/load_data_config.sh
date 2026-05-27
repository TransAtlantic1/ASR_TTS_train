#!/usr/bin/env bash

default_data_config() {
  local recipe_root="$1"
  local dataset_name="$2"
  local language="$3"
  printf '%s/data_config/%s_%s.yaml\n' "$recipe_root" "$dataset_name" "$language"
}

load_data_config() {
  local config_path="$1"
  local loader_path="$2"
  if [ -z "$config_path" ]; then
    return 0
  fi
  if [ ! -f "$config_path" ]; then
    echo "$0: missing data config ${config_path}" >&2
    exit 1
  fi
  eval "$(python3 "$loader_path" "$config_path")"
}
