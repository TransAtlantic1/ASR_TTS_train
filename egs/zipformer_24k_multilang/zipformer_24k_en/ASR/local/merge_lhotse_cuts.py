#!/usr/bin/env python3

import argparse
from pathlib import Path
from typing import Iterable, List

from lhotse import CutSet, load_manifest_lazy


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Merge multiple Lhotse CutSet manifests into one output file."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="Input CutSet manifest paths.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Merged CutSet manifest path.",
    )
    return parser


def _iter_unique_cuts(paths: Iterable[Path]):
    seen_ids = set()
    for path in paths:
        cuts = load_manifest_lazy(path)
        for cut in cuts:
            if cut.id in seen_ids:
                raise ValueError(f"Duplicate cut ID across merged manifests: {cut.id}")
            seen_ids.add(cut.id)
            yield cut


def merge_cut_manifests(inputs: List[Path], output: Path) -> Path:
    for path in inputs:
        if not path.is_file():
            raise FileNotFoundError(f"Missing CutSet manifest: {path}")

    output.parent.mkdir(parents=True, exist_ok=True)
    merged = CutSet.from_cuts(_iter_unique_cuts(inputs))
    merged.to_file(output)
    return output


def main() -> None:
    args = get_parser().parse_args()
    merge_cut_manifests(args.inputs, args.output)


if __name__ == "__main__":
    main()
