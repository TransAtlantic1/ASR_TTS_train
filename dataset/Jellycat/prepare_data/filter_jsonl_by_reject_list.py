#!/usr/bin/env python3

import argparse
import gzip
import json
from pathlib import Path
from typing import Iterable, Set


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Filter line-delimited JSON/JSONL manifests by reject-list ids.",
    )
    parser.add_argument("--reject-jsonl", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--id-field", default="id")
    return parser.parse_args()


def open_text(path: Path, mode: str):
    if path.suffix == ".gz":
        return gzip.open(path, mode, encoding="utf-8")
    return path.open(mode, encoding="utf-8")


def load_reject_ids(path: Path) -> Set[str]:
    ids = set()
    with open_text(path, "rt") as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            ids.add(str(record["id"]))
    return ids


def main() -> None:
    args = get_args()
    reject_ids = load_reject_ids(args.reject_jsonl)
    kept = 0
    dropped = 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open_text(args.input, "rt") as in_f, open_text(args.output, "wt") as out_f:
        for line in in_f:
            if not line.strip():
                continue
            record = json.loads(line)
            record_id = str(record[args.id_field])
            if record_id in reject_ids:
                dropped += 1
                continue
            out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            kept += 1

    print(f"reject_ids\t{len(reject_ids)}")
    print(f"kept\t{kept}")
    print(f"dropped\t{dropped}")
    print(f"output\t{args.output}")


if __name__ == "__main__":
    main()
