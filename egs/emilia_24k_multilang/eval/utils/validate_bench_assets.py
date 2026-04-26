#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, List, Sequence

from lhotse import CutSet
from lhotse.serialization import load_manifest_lazy_or_eager

from bench_registry import EN_DATASETS, ZH_DATASETS


def parse_csv(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _resolve_storage_path(storage_path: str, cut_manifest_path: Path) -> Path:
    path = Path(storage_path)
    if path.is_absolute():
        return path.resolve()
    return (cut_manifest_path.parent / path).resolve()


def _is_expected_sharded_lca_path(path: Path, sharded_root: Path) -> bool:
    return path.suffix == ".lca" and _is_relative_to(path, sharded_root)


def _looks_like_thchs30_pointer_text(text: str) -> bool:
    value = " ".join(str(text or "").strip().split())
    if not value:
        return False

    lower = value.lower()
    if lower.endswith(".trn") and any(sep in value for sep in ("/", "\\")):
        return True

    tokens = lower.split()
    return (
        len(tokens) >= 4
        and tokens[-2:] == ["wav", "trn"]
        and "data" in tokens
        and value.isascii()
    )


def _has_thchs30_pointer_artifact(cut) -> bool:
    for supervision in getattr(cut, "supervisions", []):
        custom = dict(getattr(supervision, "custom", None) or {})
        raw_text = custom.get("raw_text")
        if _looks_like_thchs30_pointer_text(str(raw_text or "")):
            return True
        if _looks_like_thchs30_pointer_text(
            str(getattr(supervision, "text", "") or "")
        ):
            return True
    return False


def _requires_thchs30_pointer_validation(dataset_id: str) -> bool:
    return dataset_id == "thchs30_test" or dataset_id.startswith("thchs30_noise_")


@dataclass
class DatasetValidationResult:
    dataset_id: str
    raw_cuts_path: str
    cuts_path: str
    lca_path: str
    language: str = ""
    language_label: str = ""
    total_cuts: int = 0
    run_eval_zh_checked: bool = False
    run_eval_zh_ok: bool | None = None
    issue_count: int = 0
    issues: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.issue_count == 0


ALL_DATASETS = {**ZH_DATASETS, **EN_DATASETS}
METADATA_ROOT = Path(__file__).resolve().parents[1] / "metadata"
RELAXED_GIGASPEECH_DATASET_IDS = {
    "GIGASPEECH_V1.0.0_DEV",
    "GIGASPEECH_V1.0.0_TEST",
}


def language_label(language: str) -> str:
    if language == "zh":
        return "中文"
    if language == "en":
        return "英文"
    return language


def dataset_spec_for(dataset_id: str):
    return ALL_DATASETS.get(dataset_id)


def allows_external_gigaspeech_bench_reuse(dataset_id: str) -> bool:
    return dataset_id in RELAXED_GIGASPEECH_DATASET_IDS


def metadata_paths(metadata_root: Path) -> List[Path]:
    return sorted(metadata_root.glob("*/*/metadata.json"))


def discover_available_dataset_ids(metadata_root: Path) -> List[str]:
    discovered = []
    for metadata_path in metadata_paths(metadata_root):
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        dataset_id = payload.get("dataset_id")
        if not dataset_id:
            continue
        status = payload.get("status")
        prepared_cut_path = payload.get("prepared_cut_path")
        if status == "blocked":
            continue
        if status == "prepared":
            discovered.append(dataset_id)
            continue
        if prepared_cut_path and Path(prepared_cut_path).is_file():
            discovered.append(dataset_id)
    return sorted(set(discovered))


def build_run_eval_zh_dataloader(cuts):
    from recipe_loader import load_recipe_modules

    modules = load_recipe_modules("zh")
    parser = argparse.ArgumentParser()
    modules.asr_datamodule.EmiliaAsrDataModule.add_arguments(parser)
    data_args = parser.parse_args([])
    data_args.language = "zh"
    data_args.return_cuts = True
    data_args.max_duration = 1000.0
    data_args.num_workers = 0
    data_args.transcript_source = "text"
    data_args.input_strategy = "PrecomputedFeatures"
    data_args.on_the_fly_feats = False
    datamodule = modules.asr_datamodule.EmiliaAsrDataModule(data_args)
    return datamodule.test_dataloaders(cuts)


def preflight_run_eval_zh_dataset(result: DatasetValidationResult, record) -> None:
    from run_eval import sanitize_eval_cuts

    if result.language != "zh":
        result.run_eval_zh_ok = None
        return

    result.run_eval_zh_checked = True
    try:
        cuts = load_manifest_lazy_or_eager(Path(result.cuts_path))
        if cuts is None:
            record(f"run_eval_zh preflight failed to load cuts: {result.cuts_path}")
            result.run_eval_zh_ok = False
            return

        sanitized, repaired, dropped = sanitize_eval_cuts(cuts)
        sanitized = sanitized.to_eager()
        if len(sanitized) == 0:
            record(
                "run_eval_zh preflight removed all cuts after sanitization "
                f"(repaired={repaired} dropped={dropped})"
            )
            result.run_eval_zh_ok = False
            return

        dataloader = build_run_eval_zh_dataloader(sanitized)
        batch_count = 0
        for batch in dataloader:
            batch_count += 1
            inputs = batch.get("inputs")
            if inputs is None:
                record("run_eval_zh preflight batch is missing inputs")
                break
            if inputs.ndim < 3:
                record(
                    f"run_eval_zh preflight batch has unexpected input rank: {tuple(inputs.shape)}"
                )
                break
            if inputs.shape[1] <= 0:
                record(
                    f"run_eval_zh preflight batch has non-positive frame axis: {tuple(inputs.shape)}"
                )
                break

            supervisions = batch.get("supervisions", {})
            cut_items = supervisions.get("cut") or []
            if len(cut_items) == 0:
                record("run_eval_zh preflight batch is missing supervision cuts")
                break

            num_frames = supervisions.get("num_frames")
            if num_frames is not None:
                frame_values = (
                    num_frames.tolist()
                    if hasattr(num_frames, "tolist")
                    else list(num_frames)
                )
                if any(int(value) <= 0 for value in frame_values):
                    record(
                        "run_eval_zh preflight produced a batch with non-positive "
                        f"supervision num_frames: {frame_values}"
                    )
                    break

        if batch_count == 0:
            record("run_eval_zh preflight produced no dataloader batches")

    except Exception as ex:  # noqa: BLE001
        record(f"run_eval_zh preflight failed: {type(ex).__name__}: {ex}")

    result.run_eval_zh_ok = result.issue_count == 0


def validate_dataset_assets(
    bench_root: Path,
    dataset_id: str,
    *,
    max_issues: int = 20,
    require_in_dataset_storage: bool = True,
    check_run_eval_zh: bool = True,
) -> DatasetValidationResult:
    dataset_root = (bench_root / dataset_id).absolute()
    resolved_fbank_root = (dataset_root / "fbank").resolve()
    raw_cuts_path = dataset_root / "raw_cuts" / f"{dataset_id}_cuts_raw.jsonl.gz"
    cuts_path = dataset_root / "fbank" / f"{dataset_id}_cuts.jsonl.gz"
    lca_path = dataset_root / "fbank" / f"{dataset_id}_feats.lca"
    sharded_lca_root = dataset_root / "fbank" / f"{dataset_id}_feats"
    spec = dataset_spec_for(dataset_id)

    result = DatasetValidationResult(
        dataset_id=dataset_id,
        language=spec.language if spec is not None else "",
        language_label=language_label(spec.language) if spec is not None else "",
        raw_cuts_path=str(raw_cuts_path),
        cuts_path=str(cuts_path),
        lca_path=str(lca_path),
    )

    def record(issue: str) -> None:
        result.issue_count += 1
        if len(result.issues) < max_issues:
            result.issues.append(issue)

    if not raw_cuts_path.is_file():
        record(f"missing raw cuts: {raw_cuts_path}")
    if not cuts_path.is_file():
        record(f"missing prepared cuts: {cuts_path}")
    if result.issue_count:
        return result

    seen_ids = set()
    cuts = load_manifest_lazy_or_eager(cuts_path)
    if cuts is None:
        record(f"unable to load prepared cuts: {cuts_path}")
        return result
    expected_lca = lca_path.resolve()
    expected_sharded_lca_root = sharded_lca_root.resolve()
    relax_gigaspeech_asset_checks = allows_external_gigaspeech_bench_reuse(dataset_id)

    for cut in cuts:
        result.total_cuts += 1
        if cut.id in seen_ids:
            record(f"duplicate cut id: {cut.id}")
            continue
        seen_ids.add(cut.id)

        if cut.duration <= 0:
            record(f"non-positive duration: {cut.id} duration={cut.duration}")

        if _requires_thchs30_pointer_validation(
            dataset_id
        ) and _has_thchs30_pointer_artifact(cut):
            record(f"THCHS30 transcript pointer artifact detected: {cut.id}")

        if not relax_gigaspeech_asset_checks and (
            cut.num_frames is None or cut.num_frames <= 0
        ):
            record(f"non-positive cut num_frames: {cut.id} num_frames={cut.num_frames}")

        features = getattr(cut, "features", None)
        if features is None:
            record(f"missing features manifest: {cut.id}")
            continue

        if (
            not relax_gigaspeech_asset_checks
            and getattr(features, "num_frames", None) != cut.num_frames
        ):
            record(
                f"manifest num_frames mismatch: {cut.id} "
                f"cut={cut.num_frames} features={getattr(features, 'num_frames', None)}"
            )

        storage_path = getattr(features, "storage_path", "")
        if not storage_path:
            record(f"missing storage path: {cut.id}")
            continue

        resolved_storage_path = _resolve_storage_path(storage_path, cuts_path)
        if relax_gigaspeech_asset_checks:
            if not resolved_storage_path.exists():
                record(
                    f"resolved storage path missing: {cut.id} "
                    f"storage_path={resolved_storage_path}"
                )
            if resolved_storage_path != expected_lca:
                record(
                    f"resolved storage target mismatch: {cut.id} "
                    f"storage_path={resolved_storage_path} expected={expected_lca}"
                )
        else:
            if require_in_dataset_storage and not _is_relative_to(
                resolved_storage_path, resolved_fbank_root
            ):
                record(
                    f"storage path escaped dataset fbank root: {cut.id} "
                    f"storage_path={resolved_storage_path} dataset_fbank_root={resolved_fbank_root}"
                )
            if not resolved_storage_path.exists():
                record(
                    f"resolved storage path missing: {cut.id} "
                    f"storage_path={resolved_storage_path}"
                )
            if not (
                resolved_storage_path == expected_lca
                or _is_expected_sharded_lca_path(
                    resolved_storage_path, expected_sharded_lca_root
                )
            ):
                record(
                    f"storage path mismatch: {cut.id} storage_path={resolved_storage_path} "
                    f"expected={expected_lca} or under {expected_sharded_lca_root}"
                )

        feature_matrix = cut.load_features()
        if feature_matrix.shape[0] <= 0:
            record(f"loaded feature matrix has zero frames: {cut.id}")
        if not relax_gigaspeech_asset_checks and feature_matrix.shape[0] != cut.num_frames:
            record(
                f"feature shape mismatch: {cut.id} "
                f"loaded={feature_matrix.shape[0]} declared={cut.num_frames}"
            )

    if check_run_eval_zh and result.ok:
        preflight_run_eval_zh_dataset(result, record)

    return result


def validate_datasets(
    bench_root: Path,
    dataset_ids: Sequence[str],
    *,
    max_issues: int = 20,
    require_in_dataset_storage: bool = True,
    check_run_eval_zh: bool = True,
) -> List[DatasetValidationResult]:
    return [
        validate_dataset_assets(
            bench_root,
            dataset_id,
            max_issues=max_issues,
            require_in_dataset_storage=require_in_dataset_storage,
            check_run_eval_zh=check_run_eval_zh,
        )
        for dataset_id in dataset_ids
    ]


def write_available_dataset_summary(
    results: Sequence[DatasetValidationResult], output_path: Path
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "dataset_id": result.dataset_id,
            "language": result.language_label or result.language,
            "feature_path": result.cuts_path,
            "validation_success": result.ok,
        }
        for result in sorted(results, key=lambda item: (item.language, item.dataset_id))
    ]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def get_parser():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--bench-root", type=Path, required=True)
    parser.add_argument("--datasets", type=str, default="")
    parser.add_argument("--metadata-root", type=Path, default=METADATA_ROOT)
    parser.add_argument(
        "--discover-from-metadata",
        action="store_true",
        help="Discover currently available datasets from metadata instead of --datasets.",
    )
    parser.add_argument("--max-issues", type=int, default=20)
    parser.add_argument(
        "--allow-external-storage",
        action="store_true",
        help="Allow feature storage paths outside the dataset root.",
    )
    parser.add_argument(
        "--skip-run-eval-zh-preflight",
        action="store_true",
        help="Skip the run_eval_zh-compatible dataloader preflight for Chinese datasets.",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=None,
        help="Optional JSON file that stores the minimal available-dataset summary.",
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> None:
    args = get_parser().parse_args()
    dataset_ids = parse_csv(args.datasets)
    if args.discover_from_metadata:
        dataset_ids = discover_available_dataset_ids(args.metadata_root)
    if not dataset_ids:
        raise SystemExit("No datasets were provided. Use --datasets or --discover-from-metadata.")

    results = validate_datasets(
        args.bench_root,
        dataset_ids,
        max_issues=args.max_issues,
        require_in_dataset_storage=not args.allow_external_storage,
        check_run_eval_zh=not args.skip_run_eval_zh_preflight,
    )

    if args.summary_output is not None:
        write_available_dataset_summary(results, args.summary_output)

    if args.json:
        print(
            json.dumps(
                [asdict(result) | {"ok": result.ok} for result in results],
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for result in results:
            print(
                json.dumps(
                    {
                        "dataset_id": result.dataset_id,
                        "ok": result.ok,
                        "total_cuts": result.total_cuts,
                        "issue_count": result.issue_count,
                        "issues": result.issues,
                    },
                    ensure_ascii=False,
                )
            )

    failed = [result.dataset_id for result in results if not result.ok]
    if failed:
        raise SystemExit(
            f"Asset validation failed for {len(failed)} dataset(s): {', '.join(failed)}"
        )


if __name__ == "__main__":
    main()
