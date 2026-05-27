#!/usr/bin/env python3

import argparse
import os
import re
import shlex
from pathlib import Path
from typing import Dict


KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def strip_inline_comment(line: str) -> str:
    quote = ""
    escaped = False
    for i, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in ("'", '"'):
            quote = char
            continue
        if char == "#":
            return line[:i]
    return line


def parse_scalar(value: str) -> str:
    value = value.strip()
    if value in ("", "null", "Null", "NULL", "~"):
        return ""
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        value = value[1:-1]
    elif value.lower() in ("true", "false"):
        value = value.lower()
    return os.path.expandvars(value)


def load_flat_yaml(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = strip_inline_comment(raw_line).strip()
        if not line:
            continue
        if line.startswith("- ") or ":" not in line:
            raise ValueError(
                f"{path}:{line_number}: only flat 'key: value' YAML is supported"
            )
        key, value = line.split(":", 1)
        key = key.strip()
        if not KEY_RE.fullmatch(key):
            raise ValueError(f"{path}:{line_number}: invalid shell variable key: {key}")
        values[key] = parse_scalar(value)
    return values


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load a flat YAML data config and print shell assignments."
    )
    parser.add_argument("config", type=Path)
    args = parser.parse_args()

    if not args.config.is_file():
        raise FileNotFoundError(f"Missing data config: {args.config}")

    for key, value in load_flat_yaml(args.config).items():
        print(f"{key}={shlex.quote(value)}")


if __name__ == "__main__":
    main()
