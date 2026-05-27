#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import gzip
import json
import logging
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from bench_registry import (
    BENCH2_ROOT,
    EN_DATASETS,
    ICEFALL_ROOT,
    PUBLIC_EVAL_ROOT,
    ZH_DATASETS,
    DatasetSpec,
    resolve_dataset_ids,
    specs_for,
)
from recipe_loader import load_local_module


if str(ICEFALL_ROOT) not in sys.path:
    sys.path.insert(0, str(ICEFALL_ROOT))


METADATA_ROOT = Path(__file__).resolve().parents[1] / "metadata"
PUBLIC_DOWNLOADS_ROOT = PUBLIC_EVAL_ROOT.parent / "downloads"
ACTIVE_DATASETS = {**ZH_DATASETS, **EN_DATASETS}
GIGASPEECH_24K_FBANK_ROOT = (
    ICEFALL_ROOT / "egs" / "gigaspeech_24k" / "ASR" / "data" / "fbank"
)
VOXPOPULI_DOWNLOAD_BASE_URL = "https://dl.fbaipublicfiles.com/voxpopuli"


def parse_csv(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def get_parser():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--language", type=str, required=True, choices=["zh", "en"])
    parser.add_argument("--bench-root", type=Path, default=BENCH2_ROOT)
    parser.add_argument("--metadata-root", type=Path, default=METADATA_ROOT)
    parser.add_argument("--test-sets", type=str, default="")
    parser.add_argument("--test-set-preset", type=str, default="")
    parser.add_argument("--feature-num-workers", type=int, default=8)
    parser.add_argument("--feature-batch-duration", type=float, default=600.0)
    parser.add_argument("--feature-device", type=str, default="auto")
    parser.add_argument("--skip-unavailable", action="store_true")
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--force-rebuild", action="store_true")
    return parser


def mkdirs(bench_root: Path) -> None:
    for relative in ("registry", "logs", "_shared_manifests"):
        (bench_root / relative).mkdir(parents=True, exist_ok=True)


def run_command(cmd: List[str], cwd: Path | None = None) -> None:
    logging.info("Running: %s", " ".join(str(part) for part in cmd))
    subprocess.run(cmd, check=True, cwd=str(cwd) if cwd is not None else None)


def metadata_language_root(metadata_root: Path, language: str) -> Path:
    return metadata_root / language


def metadata_dir_for_spec(spec: DatasetSpec, metadata_root: Path) -> Path:
    return metadata_language_root(metadata_root, spec.language) / spec.dataset_id


def cleanup_legacy_metadata_tree(metadata_root: Path) -> None:
    metadata_root.mkdir(parents=True, exist_ok=True)
    for language in ("zh", "en"):
        metadata_language_root(metadata_root, language).mkdir(parents=True, exist_ok=True)

    if metadata_root != METADATA_ROOT:
        return

    for child in sorted(METADATA_ROOT.iterdir()):
        if not child.is_dir() or child.name in {"zh", "en"}:
            continue
        if child.name.startswith("speechio_") or child.name == "speechio_public_all":
            shutil.rmtree(child, ignore_errors=True)
            continue

        spec = ACTIVE_DATASETS.get(child.name)
        metadata_path = child / "metadata.json"
        if spec is None or not metadata_path.is_file():
            continue

        target_dir = metadata_dir_for_spec(spec, metadata_root)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / "metadata.json"
        if not target_path.exists():
            shutil.move(str(metadata_path), str(target_path))
        try:
            child.rmdir()
        except OSError:
            pass


def write_dataset_metadata(
    spec: DatasetSpec,
    bench_root: Path,
    output_cuts_path: Path,
    metadata_root: Path = METADATA_ROOT,
    *,
    status: str = "prepared",
) -> None:
    metadata_dir = metadata_dir_for_spec(spec, metadata_root)
    metadata_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "dataset_id": spec.dataset_id,
        "language": spec.language,
        "difficulty": spec.difficulty,
        "description": spec.description,
        "source_url": spec.source_url,
        "manual_download": spec.manual_download,
        "prep_kind": spec.prep_kind,
        "status": status,
        "bench_dataset_root": str((bench_root / spec.dataset_id).absolute()),
        "prepared_cut_path": str(output_cuts_path.absolute()),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    metadata_path = metadata_dir / "metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_unavailable_dataset_metadata(
    spec: DatasetSpec,
    bench_root: Path,
    error_message: str,
    metadata_root: Path = METADATA_ROOT,
) -> None:
    metadata_dir = metadata_dir_for_spec(spec, metadata_root)
    metadata_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "dataset_id": spec.dataset_id,
        "language": spec.language,
        "difficulty": spec.difficulty,
        "description": spec.description,
        "source_url": spec.source_url,
        "manual_download": spec.manual_download,
        "prep_kind": spec.prep_kind,
        "status": "blocked",
        "bench_dataset_root": str((bench_root / spec.dataset_id).absolute()),
        "expected_existing_cut_candidates": list(spec.existing_cut_candidates),
        "blocked_reason": error_message,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    metadata_path = metadata_dir / "metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_existing_registry(registry_path: Path) -> Dict[str, str]:
    if not registry_path.is_file():
        return {}
    existing: Dict[str, str] = {}
    with open(registry_path, "r", encoding="utf-8") as f:
        next(f, None)
        for line in f:
            line = line.strip()
            if not line:
                continue
            dataset_id, cuts_path = line.split("\t", maxsplit=1)
            existing[dataset_id] = cuts_path
    return existing


def load_manifest(path: Path):
    from lhotse.serialization import load_manifest_lazy_or_eager

    manifest = load_manifest_lazy_or_eager(path)
    if manifest is None:
        raise ValueError(f"Unable to load manifest: {path}")
    return manifest


def _normalize_text(language: str, text: str) -> str:
    text_norm = load_local_module(language, "text_normalization")
    return text_norm.normalize_text(text, language)


def standardize_supervision(supervision, language: str, dataset_id: str):
    from lhotse.utils import fastcopy

    raw_text = str(
        ((getattr(supervision, "custom", None) or {}).get("raw_text"))
        or supervision.text
        or ""
    ).strip()
    normalized = _normalize_text(language, raw_text)
    if not normalized:
        return None
    custom = dict(getattr(supervision, "custom", None) or {})
    custom["raw_text"] = raw_text
    custom["dataset_id"] = dataset_id
    return fastcopy(supervision, text=normalized, custom=custom)


def standardize_cutset(cut_set, language: str, dataset_id: str):
    from lhotse import CutSet
    from lhotse.utils import fastcopy

    new_cuts = []
    for cut in cut_set:
        new_supervisions = []
        for supervision in cut.supervisions:
            standardized = standardize_supervision(supervision, language, dataset_id)
            if standardized is not None:
                new_supervisions.append(standardized)
        if not new_supervisions:
            continue
        new_cuts.append(fastcopy(cut, supervisions=new_supervisions))
    if not new_cuts:
        raise ValueError(f"No usable cuts left after standardization for {dataset_id}")
    return _align_trimmed_single_supervision_durations(
        CutSet.from_cuts(new_cuts).trim_to_supervisions(
            keep_overlapping=False, min_duration=None
        )
    )


def _align_trimmed_single_supervision_durations(cut_set, tolerance: float = 1.0e-4):
    from lhotse import CutSet
    from lhotse.utils import fastcopy

    repaired = []
    for cut in cut_set:
        if len(cut.supervisions) != 1:
            repaired.append(cut)
            continue

        supervision = cut.supervisions[0]
        if abs(supervision.start) > 1.0e-6:
            repaired.append(cut)
            continue

        if abs(supervision.duration - cut.duration) <= 1.0e-6:
            repaired.append(cut)
            continue

        if abs(supervision.duration - cut.duration) <= tolerance:
            repaired.append(
                fastcopy(
                    cut,
                    supervisions=[fastcopy(supervision, duration=cut.duration)],
                )
            )
            continue

        repaired.append(cut)

    return CutSet.from_cuts(repaired)


def build_cutset_from_manifests(recordings, supervisions, language: str, dataset_id: str):
    from lhotse import CutSet, SupervisionSet

    standardized = []
    for supervision in supervisions:
        item = standardize_supervision(supervision, language, dataset_id)
        if item is not None:
            standardized.append(item)
    if not standardized:
        raise ValueError(f"No standardized supervisions for {dataset_id}")
    cut_set = CutSet.from_manifests(
        recordings=recordings,
        supervisions=SupervisionSet.from_segments(standardized),
    )
    return _align_trimmed_single_supervision_durations(
        cut_set.trim_to_supervisions(keep_overlapping=False, min_duration=None)
    )


def feature_paths(bench_root: Path, dataset_id: str) -> Tuple[Path, Path, str]:
    dataset_root = bench_root / dataset_id
    out_dir = dataset_root / "fbank"
    raw_dir = dataset_root / "raw_cuts"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_cuts_path = raw_dir / f"{dataset_id}_cuts_raw.jsonl.gz"
    output_cuts_path = out_dir / f"{dataset_id}_cuts.jsonl.gz"
    storage_path = str(out_dir / f"{dataset_id}_feats")
    return raw_cuts_path, output_cuts_path, storage_path


def feature_storage_index_path(bench_root: Path, dataset_id: str) -> Path:
    _, output_cuts_path, _ = feature_paths(bench_root, dataset_id)
    return output_cuts_path.parent / f"{dataset_id}_feats.lca"


def clear_feature_outputs(bench_root: Path, dataset_id: str) -> None:
    raw_cuts_path, output_cuts_path, _ = feature_paths(bench_root, dataset_id)
    storage_index_path = feature_storage_index_path(bench_root, dataset_id)
    for path in (raw_cuts_path, output_cuts_path, storage_index_path):
        if path.exists() or path.is_symlink():
            path.unlink()


def assert_prepared_cutset_invariants(cut_set, dataset_id: str) -> None:
    seen_ids = set()
    for cut in cut_set:
        if cut.id in seen_ids:
            raise ValueError(f"Duplicate cut id detected for {dataset_id}: {cut.id}")
        seen_ids.add(cut.id)

        if cut.duration <= 0:
            raise ValueError(
                f"Non-positive cut duration detected for {dataset_id}: {cut.id}"
            )

        if len(cut.supervisions) != 1:
            raise ValueError(
                f"Expected exactly one supervision per cut for {dataset_id}: "
                f"{cut.id} has {len(cut.supervisions)}"
            )

        supervision = cut.supervisions[0]
        if abs(supervision.start) > 1.0e-6:
            raise ValueError(
                f"Expected trimmed supervision start=0.0 for {dataset_id}: "
                f"{cut.id} starts at {supervision.start}"
            )
        if abs(supervision.duration - cut.duration) > 1.0e-6:
            raise ValueError(
                f"Expected trimmed cut/supervision durations to match for "
                f"{dataset_id}: {cut.id} cut={cut.duration} supervision={supervision.duration}"
            )


def _symlink_if_missing(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        return
    target.symlink_to(source)


def maybe_link_existing_gigaspeech_outputs(
    spec: DatasetSpec, bench_root: Path
) -> Path | None:
    split = spec.extra["split"]
    source_cuts = GIGASPEECH_24K_FBANK_ROOT / f"gigaspeech_cuts_{split}.jsonl.gz"
    if not source_cuts.is_file():
        return None

    raw_cuts_path, output_cuts_path, _ = feature_paths(bench_root, spec.dataset_id)
    source_raw_cuts = GIGASPEECH_24K_FBANK_ROOT / f"gigaspeech_cuts_{split}_raw.jsonl.gz"
    source_lca = GIGASPEECH_24K_FBANK_ROOT / f"gigaspeech_feats_{split}.lca"
    target_lca = output_cuts_path.parent / f"{spec.dataset_id}_feats.lca"

    _symlink_if_missing(source_cuts, output_cuts_path)
    if source_raw_cuts.is_file():
        _symlink_if_missing(source_raw_cuts, raw_cuts_path)
    if source_lca.is_file():
        _symlink_if_missing(source_lca, target_lca)

    logging.info(
        "Reused existing GigaSpeech %s outputs from %s",
        split,
        GIGASPEECH_24K_FBANK_ROOT,
    )
    return output_cuts_path


def maybe_link_existing_prepared_outputs(
    spec: DatasetSpec, bench_root: Path
) -> Path | None:
    for source_dataset_id in spec.existing_prepared_dataset_ids:
        source_root = bench_root / source_dataset_id
        source_cuts = source_root / "fbank" / f"{source_dataset_id}_cuts.jsonl.gz"
        if not source_cuts.is_file():
            continue

        raw_cuts_path, output_cuts_path, _ = feature_paths(bench_root, spec.dataset_id)
        source_raw_cuts = (
            source_root / "raw_cuts" / f"{source_dataset_id}_cuts_raw.jsonl.gz"
        )
        source_lca = source_root / "fbank" / f"{source_dataset_id}_feats.lca"
        target_lca = output_cuts_path.parent / f"{spec.dataset_id}_feats.lca"

        _symlink_if_missing(source_cuts, output_cuts_path)
        if source_raw_cuts.is_file():
            _symlink_if_missing(source_raw_cuts, raw_cuts_path)
        if source_lca.is_file():
            _symlink_if_missing(source_lca, target_lca)

        logging.info(
            "Reused existing prepared outputs for %s from %s",
            spec.dataset_id,
            source_root,
        )
        return output_cuts_path

    return None


def maybe_resume_feature_outputs(
    language: str,
    bench_root: Path,
    dataset_id: str,
    num_workers: int,
    batch_duration: float,
    device: str,
    *,
    force_rebuild: bool = False,
) -> Path | None:
    if force_rebuild:
        clear_feature_outputs(bench_root, dataset_id)
        return None

    raw_cuts_path, output_cuts_path, storage_path = feature_paths(bench_root, dataset_id)
    if output_cuts_path.is_file():
        logging.info("Reusing existing prepared cuts for %s", dataset_id)
        return output_cuts_path
    if raw_cuts_path.is_file():
        compute_emilia_features(
            language=language,
            raw_cuts_path=raw_cuts_path,
            output_cuts_path=output_cuts_path,
            storage_path=storage_path,
            num_workers=num_workers,
            batch_duration=batch_duration,
            device=device,
        )
        return output_cuts_path
    return None


def compute_emilia_features(
    language: str,
    raw_cuts_path: Path,
    output_cuts_path: Path,
    storage_path: str,
    num_workers: int,
    batch_duration: float,
    device: str,
) -> None:
    script = Path(__file__).resolve().parent / "compute_eval_features.py"
    run_command(
        [
            "python3",
            str(script),
            "--language",
            language,
            "--raw-cuts-path",
            str(raw_cuts_path),
            "--output-cuts-path",
            str(output_cuts_path),
            "--storage-path",
            storage_path,
            "--num-workers",
            str(num_workers),
            "--batch-duration",
            str(batch_duration),
            "--device",
            device,
        ]
    )


def write_cutset_and_compute_features(
    cut_set,
    language: str,
    bench_root: Path,
    dataset_id: str,
    num_workers: int,
    batch_duration: float,
    device: str,
) -> Path:
    from validate_bench_assets import validate_dataset_assets

    raw_cuts_path, output_cuts_path, storage_path = feature_paths(bench_root, dataset_id)
    if output_cuts_path.is_file():
        return output_cuts_path
    assert_prepared_cutset_invariants(cut_set, dataset_id)
    if not raw_cuts_path.is_file():
        cut_set.to_file(raw_cuts_path)
    compute_emilia_features(
        language=language,
        raw_cuts_path=raw_cuts_path,
        output_cuts_path=output_cuts_path,
        storage_path=storage_path,
        num_workers=num_workers,
        batch_duration=batch_duration,
        device=device,
    )
    validation_result = validate_dataset_assets(bench_root, dataset_id)
    if not validation_result.ok:
        raise ValueError(
            f"Prepared asset validation failed for {dataset_id}: "
            + "; ".join(validation_result.issues)
        )
    return output_cuts_path


def shared_download_dir(family: str) -> Path:
    path = PUBLIC_DOWNLOADS_ROOT / family
    path.mkdir(parents=True, exist_ok=True)
    return path


def shared_manifests_dir(bench_root: Path, family: str) -> Path:
    path = bench_root / "_shared_manifests" / family
    path.mkdir(parents=True, exist_ok=True)
    return path


def download_url(url: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.is_file():
        logging.info("Reusing existing download: %s", output_path)
        return
    logging.info("Downloading %s -> %s", url, output_path)
    urllib.request.urlretrieve(url, output_path)


def _resolve_thchs30_root(download_dir: Path) -> Path:
    candidates = [
        download_dir / "thchs30",
        download_dir / "thchs" / "data_thchs30",
        download_dir / "data_thchs30",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    for path in download_dir.rglob("data_thchs30"):
        if path.is_dir():
            return path
    raise FileNotFoundError(f"Unable to locate THCHS-30 corpus under {download_dir}")


def _find_thchs30_noise_root(download_dir: Path) -> Path:
    candidates = [download_dir / "test-noise", download_dir / "thchs30_noise"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    archive_path = download_dir / "test-noise.tgz"
    if not archive_path.is_file():
        download_url("https://www.openslr.org/resources/18/test-noise.tgz", archive_path)
    target_dir = download_dir / "test-noise"
    if not target_dir.exists():
        with tarfile.open(archive_path) as tar:
            tar.extractall(download_dir)
    if target_dir.exists():
        return target_dir
    for path in download_dir.rglob("*"):
        if path.is_dir() and path.name.lower() == "test-noise":
            return path
    raise FileNotFoundError(f"Unable to locate extracted THCHS-30 noise data under {download_dir}")


def _thchs_noise_label(path: Path, noise_root: Path) -> str:
    try:
        parts = [part.lower() for part in path.relative_to(noise_root).parts]
    except ValueError as exc:
        raise ValueError(
            f"Unable to infer THCHS-30 noise type outside noise root: {path}"
        ) from exc

    for part in parts:
        if part in {"white", "car", "cafe"}:
            return part
    raise ValueError(f"Unable to infer THCHS-30 noise type from {path}")


def _load_transcript(path: Path) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.readline().strip()


def _load_thchs30_noise_transcript(path: Path) -> str:
    text = _load_transcript(path)
    visited = {path.resolve()}

    while text.endswith(".trn") and any(sep in text for sep in ("/", "\\")):
        target = (path.parent / text).resolve()
        if target in visited or not target.is_file():
            break
        visited.add(target)
        path = target
        text = _load_transcript(path)

    return text


def _load_thchs30_transcript(path: Path) -> str:
    return _load_thchs30_noise_transcript(path)


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


def _has_thchs30_pointer_artifact(supervisions) -> bool:
    for supervision in supervisions:
        custom = dict(getattr(supervision, "custom", None) or {})
        raw_text = custom.get("raw_text")
        if _looks_like_thchs30_pointer_text(str(raw_text or "")):
            return True
        if _looks_like_thchs30_pointer_text(
            str(getattr(supervision, "text", "") or "")
        ):
            return True
    return False


def _resolve_thchs30_transcript(thchs_root: Path, wav_path: Path) -> Path:
    candidates = [
        wav_path.with_suffix(".trn"),
        wav_path.with_suffix(".wav.trn"),
        thchs_root / "test" / f"{wav_path.stem}.wav.trn",
        thchs_root / "test" / f"{wav_path.stem}.trn",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"Missing transcript for {wav_path}")


def _build_thchs30_subset_manifests(corpus_root: Path, subset: str):
    from lhotse import Recording, RecordingSet, SupervisionSet
    from lhotse.supervision import SupervisionSegment

    subset_dir = corpus_root / subset
    if not subset_dir.is_dir():
        raise FileNotFoundError(f"Missing THCHS-30 subset directory: {subset_dir}")

    recordings = []
    supervisions = []
    for wav_path in sorted(subset_dir.glob("*.wav")):
        trn_path = wav_path.with_suffix(".wav.trn")
        if not trn_path.is_file():
            trn_path = wav_path.with_suffix(".trn")
        if not trn_path.is_file():
            continue
        recording = Recording.from_file(str(wav_path), recording_id=wav_path.stem)
        text = _load_thchs30_transcript(trn_path)
        recordings.append(recording)
        supervisions.append(
            SupervisionSegment(
                id=recording.id,
                recording_id=recording.id,
                start=0.0,
                duration=recording.duration,
                channel=0,
                text=text,
                language="zh",
                custom={"raw_text": text},
            )
        )
    if not recordings:
        raise RuntimeError(f"No THCHS-30 recordings found in {subset_dir}")
    return RecordingSet.from_recordings(recordings), SupervisionSet.from_segments(supervisions)


def _find_manifest_path(
    manifest_dir: Path, kind: str, split: str, extra_fragments: Iterable[str] = ()
) -> Path:
    matches = []
    split_lower = split.lower()
    fragments = [fragment.lower() for fragment in extra_fragments if fragment]
    for path in sorted(manifest_dir.glob(f"*{kind}*.jsonl.gz")):
        name = path.name.lower()
        if split_lower not in name:
            continue
        if all(fragment in name for fragment in fragments):
            matches.append(path)
    if not matches:
        raise FileNotFoundError(
            f"Could not find {kind} manifest for split={split} under {manifest_dir}"
        )
    return matches[0]


def resolve_manifest_pair(
    manifest_dir: Path, split: str, extra_fragments: Iterable[str] = ()
) -> Tuple[Path, Path]:
    recordings = _find_manifest_path(manifest_dir, "recordings", split, extra_fragments)
    supervisions = _find_manifest_path(
        manifest_dir, "supervisions", split, extra_fragments
    )
    return recordings, supervisions


def _resolve_existing_cut(spec: DatasetSpec) -> Path:
    for candidate in spec.existing_cut_candidates:
        path = ICEFALL_ROOT / candidate
        if path.is_file():
            return path
    raise FileNotFoundError(
        f"Could not locate an existing cut manifest for {spec.dataset_id}. "
        f"Tried: {', '.join(spec.existing_cut_candidates)}"
    )


def _resolve_tedlium_root(download_dir: Path) -> Path:
    candidates = [download_dir / "tedlium3", download_dir / "TEDLIUM_release-3"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Unable to locate TEDLIUM3 under {download_dir}")


def _ensure_librispeech_manifests(bench_root: Path) -> Tuple[Path, Path]:
    download_dir = shared_download_dir("librispeech")
    manifests_dir = shared_manifests_dir(bench_root, "librispeech")
    corpus_root = download_dir / "LibriSpeech"
    if not corpus_root.exists():
        run_command(["lhotse", "download", "librispeech", "--full", str(download_dir)])
    if not list(manifests_dir.glob("*recordings_test-clean.jsonl.gz")):
        run_command(["lhotse", "prepare", "librispeech", str(corpus_root), str(manifests_dir)])
    return corpus_root, manifests_dir


def _ensure_tedlium_manifests(bench_root: Path) -> Tuple[Path, Path]:
    download_dir = shared_download_dir("tedlium3")
    manifests_dir = shared_manifests_dir(bench_root, "tedlium3")
    try:
        corpus_root = _resolve_tedlium_root(download_dir)
    except FileNotFoundError:
        run_command(["lhotse", "download", "tedlium", str(download_dir)])
        source_dir = download_dir / "TEDLIUM_release-3"
        target_dir = download_dir / "tedlium3"
        if source_dir.exists() and not target_dir.exists():
            shutil.move(str(source_dir), str(target_dir))
        corpus_root = _resolve_tedlium_root(download_dir)
    if not list(manifests_dir.glob("*recordings_dev.jsonl.gz")):
        run_command(["lhotse", "prepare", "tedlium", str(corpus_root), str(manifests_dir)])
    return corpus_root, manifests_dir


def _resolve_gigaspeech_password_file(download_dir: Path) -> Path:
    env_value = os.environ.get("GIGASPEECH_PASSWORD_FILE")
    if env_value:
        path = Path(env_value)
        if path.is_file():
            return path
    path = download_dir / "password"
    if path.is_file():
        return path
    raise FileNotFoundError(
        f"GigaSpeech download requires a password file at {path} or GIGASPEECH_PASSWORD_FILE."
    )


def _ensure_gigaspeech_manifests(bench_root: Path) -> Tuple[Path, Path]:
    download_dir = shared_download_dir("gigaspeech")
    manifests_dir = shared_manifests_dir(bench_root, "gigaspeech")
    corpus_root = download_dir / "GigaSpeech"
    if not corpus_root.exists():
        password_file = _resolve_gigaspeech_password_file(download_dir)
        run_command(
            [
                "lhotse",
                "download",
                "gigaspeech",
                "--host",
                "magicdata",
                "--subset",
                "DEV",
                "--subset",
                "TEST",
                str(password_file),
                str(corpus_root),
            ]
        )
    if not list(manifests_dir.glob("*recordings_DEV.jsonl.gz")):
        run_command(
            [
                "lhotse",
                "prepare",
                "gigaspeech",
                "--subset",
                "DEV",
                "--subset",
                "TEST",
                str(corpus_root),
                str(manifests_dir),
            ]
        )
    return corpus_root, manifests_dir


def _ensure_voxpopuli_manifests(bench_root: Path) -> Tuple[Path, Path]:
    download_dir = shared_download_dir("voxpopuli")
    manifests_dir = shared_manifests_dir(bench_root, "voxpopuli-en")
    if not (download_dir / "raw_audios" / "en").exists():
        run_command(
            ["lhotse", "download", "voxpopuli", "--subset", "en", str(download_dir)]
        )
    if not list(manifests_dir.glob("*recordings_dev.jsonl.gz")):
        run_command(
            [
                "lhotse",
                "prepare",
                "voxpopuli",
                "--task",
                "asr",
                "--lang",
                "en",
                str(download_dir),
                str(manifests_dir),
            ]
        )
    return download_dir, manifests_dir


def _download_to_path_if_missing(url: str, output_path: Path) -> Path:
    if output_path.is_file():
        return output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    logging.info("Downloading %s -> %s", url, output_path)
    urllib.request.urlretrieve(url, output_path)
    return output_path


def _parse_truthy_flag(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _voxpopuli_recording_id(path: Path, language: str = "en") -> str:
    recording_id = path.stem
    suffix = f"_{language}"
    if recording_id.endswith(suffix):
        recording_id = recording_id[: -len(suffix)]
    if recording_id.endswith("_original"):
        recording_id = recording_id[: -len("_original")]
    return recording_id


def _build_voxpopuli_accented_test_manifests(base_recordings, annotations_path: Path):
    from lhotse import SupervisionSet
    from lhotse.supervision import SupervisionSegment

    segments = []
    num_segments = defaultdict(int)
    with gzip.open(annotations_path, "rt", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="|"):
            if str(row.get("split") or "").strip().lower() != "test":
                continue

            accent = str(row.get("accent") or "").strip()
            if not accent:
                continue

            reco_id = str(row["session_id"]).strip()
            start_time = float(row["start_time"])
            duration = float(row["end_time"]) - start_time

            num_segments[reco_id] += 1
            segments.append(
                SupervisionSegment(
                    id=f"{reco_id}-{num_segments[reco_id]}",
                    recording_id=reco_id,
                    start=round(start_time, ndigits=8),
                    duration=round(duration, ndigits=8),
                    channel=0,
                    language="en",
                    speaker=row.get("speaker_id"),
                    gender=row.get("gender"),
                    text=row["normed_text"],
                    custom={
                        "orig_text": row.get("original_text", ""),
                        "accent": accent,
                        "is_gold_transcript": _parse_truthy_flag(
                            row.get("is_gold_transcript")
                        ),
                    },
                )
            )

    if not segments:
        raise FileNotFoundError(
            "The official VoxPopuli accented annotations did not yield any accented test segments."
        )

    recording_ids = {segment.recording_id for segment in segments}
    available_recording_ids = {recording.id for recording in base_recordings}
    missing_recording_ids = sorted(recording_ids - available_recording_ids)
    if missing_recording_ids:
        preview = ", ".join(missing_recording_ids[:10])
        raise FileNotFoundError(
            "The official VoxPopuli accented annotations reference recordings "
            f"missing from the available VoxPopuli English recording pool; first ids: {preview}"
        )

    recordings = base_recordings.filter(lambda recording: recording.id in recording_ids)
    return recordings, SupervisionSet.from_segments(segments)


def _ensure_voxpopuli_accented_test_manifests(bench_root: Path) -> Tuple[Path, Path]:
    from lhotse import RecordingSet

    download_dir, manifests_dir = _ensure_voxpopuli_manifests(bench_root)
    accented_recordings_path = (
        manifests_dir / "voxpopuli-asr-en_accented_recordings_test.jsonl.gz"
    )
    accented_supervisions_path = (
        manifests_dir / "voxpopuli-asr-en_accented_supervisions_test.jsonl.gz"
    )
    if accented_recordings_path.is_file() and accented_supervisions_path.is_file():
        return accented_recordings_path, accented_supervisions_path

    accented_annotations_path = manifests_dir / "asr_en_accented.tsv.gz"
    _download_to_path_if_missing(
        f"{VOXPOPULI_DOWNLOAD_BASE_URL}/annotations/asr/asr_en_accented.tsv.gz",
        accented_annotations_path,
    )
    accented_audio_root = download_dir / "raw_audios" / "original"
    if not accented_audio_root.exists():
        run_command(
            ["lhotse", "download", "voxpopuli", "--subset", "asr", str(download_dir)]
        )

    base_recordings = RecordingSet.from_dir(
        accented_audio_root,
        "*.ogg",
        recording_id=_voxpopuli_recording_id,
    )
    recordings, supervisions = _build_voxpopuli_accented_test_manifests(
        base_recordings, accented_annotations_path
    )
    recordings.to_file(accented_recordings_path)
    supervisions.to_file(accented_supervisions_path)
    return accented_recordings_path, accented_supervisions_path


def _ensure_commonvoice_manifests(bench_root: Path, release: str) -> Tuple[Path, Path]:
    download_dir = shared_download_dir("commonvoice")
    manifests_dir = shared_manifests_dir(bench_root, "commonvoice-en")
    if not (download_dir / release / "en" / "clips").exists():
        run_command(
            [
                "lhotse",
                "download",
                "commonvoice",
                "--languages",
                "en",
                "--release",
                release,
                str(download_dir),
            ]
        )
    if not list(manifests_dir.glob("*recordings_dev.jsonl.gz")):
        run_command(
            [
                "lhotse",
                "prepare",
                "commonvoice",
                "--language",
                "en",
                str(download_dir / release),
                str(manifests_dir),
            ]
        )
    return download_dir, manifests_dir


def _ensure_aishell_manifests(bench_root: Path) -> Tuple[Path, Path]:
    download_dir = shared_download_dir("aishell")
    manifests_dir = shared_manifests_dir(bench_root, "aishell")
    if not (download_dir / "aishell").exists():
        run_command(["lhotse", "download", "aishell", str(download_dir)])
    if not list(manifests_dir.glob("*recordings_test.jsonl.gz")):
        run_command(["lhotse", "prepare", "aishell", str(download_dir / "aishell"), str(manifests_dir)])
    return download_dir, manifests_dir


def _ensure_alimeeting_manifests(bench_root: Path, mic: str) -> Tuple[Path, Path]:
    download_dir = shared_download_dir("alimeeting")
    manifests_dir = shared_manifests_dir(bench_root, "alimeeting")
    if not (download_dir / "Train_Ali_far.tar.gz").exists():
        run_command(["lhotse", "download", "ali-meeting", str(download_dir)])
    if not list(manifests_dir.glob(f"*{mic}*recordings_eval.jsonl.gz")):
        run_command(
            [
                "lhotse",
                "prepare",
                "ali-meeting",
                "--mic",
                mic,
                "--save-mono",
                str(download_dir),
                str(manifests_dir),
            ]
        )
    return download_dir, manifests_dir


def _resolve_aishell2_root() -> Path:
    candidates = [
        shared_download_dir("aishell2"),
        PUBLIC_DOWNLOADS_ROOT / "AISHELL-2",
    ]
    for candidate in candidates:
        if (candidate / "AISHELL-2").exists():
            return candidate / "AISHELL-2"
        if candidate.name == "AISHELL-2" and candidate.exists():
            return candidate
        for path in candidate.rglob("AISHELL-2"):
            if path.is_dir():
                return path
    raise FileNotFoundError(
        f"AISHELL-2 manual data was not found under {shared_download_dir('aishell2')}"
    )


def _resolve_aishell2_channel_root(corpus_root: Path, channel: str) -> Path:
    target = {"ios": "ios", "android": "android", "mic": "mic"}[channel.lower()]
    for path in corpus_root.iterdir():
        if path.is_dir() and path.name.lower() == target:
            return path
    raise FileNotFoundError(f"Could not find AISHELL-2 channel={channel} under {corpus_root}")


def _parse_transcript_table(path: Path) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2:
                mapping[parts[0]] = parts[1]
    return mapping


def _build_aishell2_subset_manifests(channel_root: Path, split: str, language: str):
    from lhotse import Recording, RecordingSet, SupervisionSet
    from lhotse.supervision import SupervisionSegment

    split_root = channel_root / split
    wav_root = split_root / "wav"
    transcript_path = split_root / "trans.txt"
    if not wav_root.is_dir() or not transcript_path.is_file():
        raise FileNotFoundError(f"Missing AISHELL-2 split data under {split_root}")

    transcripts = _parse_transcript_table(transcript_path)
    recordings = []
    supervisions = []
    for wav_path in sorted(wav_root.rglob("*.wav")):
        text = transcripts.get(wav_path.stem)
        if not text:
            continue
        recording = Recording.from_file(str(wav_path), recording_id=wav_path.stem)
        recordings.append(recording)
        supervisions.append(
            SupervisionSegment(
                id=recording.id,
                recording_id=recording.id,
                start=0.0,
                duration=recording.duration,
                channel=0,
                text=text,
                language=language,
                custom={"raw_text": text},
            )
        )
    if not recordings:
        raise RuntimeError(f"No AISHELL-2 wavs found in {wav_root}")
    return RecordingSet.from_recordings(recordings), SupervisionSet.from_segments(supervisions)


def _supervision_has_accent(supervision) -> bool:
    custom = dict(getattr(supervision, "custom", None) or {})
    for key in ("accent", "accented", "speaker_accent", "accent_type"):
        value = custom.get(key)
        if isinstance(value, str) and value.strip():
            return True
    return False


def filter_accented_cutset(cut_set):
    from lhotse import CutSet

    retained = []
    for cut in cut_set:
        if any(_supervision_has_accent(supervision) for supervision in cut.supervisions):
            retained.append(cut)
    if not retained:
        raise FileNotFoundError(
            "No accent-tagged supervision metadata was found in the prepared VoxPopuli manifests."
        )
    return CutSet.from_cuts(retained)


def prepare_thchs30_clean(
    spec: DatasetSpec,
    bench_root: Path,
    num_workers: int,
    batch_duration: float,
    device: str,
    force_rebuild: bool = False,
) -> Path:
    resumed = maybe_resume_feature_outputs(
        spec.language,
        bench_root,
        spec.dataset_id,
        num_workers,
        batch_duration,
        device,
        force_rebuild=force_rebuild,
    )
    if resumed is not None:
        return resumed
    dataset_root = bench_root / spec.dataset_id
    download_dir = dataset_root / "download"
    try:
        thchs_root = _resolve_thchs30_root(download_dir)
    except FileNotFoundError:
        run_command(["lhotse", "download", "thchs-30", str(download_dir)])
        thchs_root = _resolve_thchs30_root(download_dir)
    manifests_dir = dataset_root / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    recordings_path = manifests_dir / "thchs_30_recordings_test.jsonl.gz"
    supervisions_path = manifests_dir / "thchs_30_supervisions_test.jsonl.gz"
    rebuild_manifests = not recordings_path.is_file() or not supervisions_path.is_file()
    if not rebuild_manifests:
        recordings = load_manifest(recordings_path)
        supervisions = load_manifest(supervisions_path)
        rebuild_manifests = _has_thchs30_pointer_artifact(supervisions)
    if rebuild_manifests:
        recordings, supervisions = _build_thchs30_subset_manifests(thchs_root, "test")
        recordings.to_file(recordings_path)
        supervisions.to_file(supervisions_path)
    cut_set = build_cutset_from_manifests(recordings, supervisions, "zh", spec.dataset_id)
    return write_cutset_and_compute_features(
        cut_set, "zh", bench_root, spec.dataset_id, num_workers, batch_duration, device
    )


def prepare_thchs30_noise(
    spec: DatasetSpec,
    bench_root: Path,
    num_workers: int,
    batch_duration: float,
    device: str,
    force_rebuild: bool = False,
) -> Path:
    resumed = maybe_resume_feature_outputs(
        spec.language,
        bench_root,
        spec.dataset_id,
        num_workers,
        batch_duration,
        device,
        force_rebuild=force_rebuild,
    )
    if resumed is not None:
        return resumed
    from lhotse import Recording, RecordingSet, SupervisionSet
    from lhotse.supervision import SupervisionSegment

    dataset_root = bench_root / spec.dataset_id
    download_dir = dataset_root / "download"
    try:
        thchs_root = _resolve_thchs30_root(download_dir)
    except FileNotFoundError:
        run_command(["lhotse", "download", "thchs-30", str(download_dir)])
        thchs_root = _resolve_thchs30_root(download_dir)
    noise_root = _find_thchs30_noise_root(download_dir)
    recordings = []
    supervisions = []
    for wav_path in sorted(noise_root.rglob("*.wav")):
        try:
            noise_type = _thchs_noise_label(wav_path, noise_root)
        except ValueError:
            continue
        if spec.dataset_id.endswith(noise_type):
            try:
                trn_path = _resolve_thchs30_transcript(thchs_root, wav_path)
            except FileNotFoundError:
                continue
            recording = Recording.from_file(str(wav_path), recording_id=wav_path.stem)
            text = _load_thchs30_noise_transcript(trn_path)
            recordings.append(recording)
            supervisions.append(
                SupervisionSegment(
                    id=recording.id,
                    recording_id=recording.id,
                    start=0.0,
                    duration=recording.duration,
                    channel=0,
                    text=text,
                    language="zh",
                    custom={"raw_text": text},
                )
            )
    if not recordings:
        raise RuntimeError(f"No THCHS-30 noise wavs matched {spec.dataset_id}")
    cut_set = build_cutset_from_manifests(
        RecordingSet.from_recordings(recordings),
        SupervisionSet.from_segments(supervisions),
        "zh",
        spec.dataset_id,
    )
    return write_cutset_and_compute_features(
        cut_set, "zh", bench_root, spec.dataset_id, num_workers, batch_duration, device
    )


def prepare_alimeeting_split(
    spec: DatasetSpec,
    bench_root: Path,
    num_workers: int,
    batch_duration: float,
    device: str,
    force_rebuild: bool = False,
) -> Path:
    resumed = maybe_resume_feature_outputs(
        spec.language,
        bench_root,
        spec.dataset_id,
        num_workers,
        batch_duration,
        device,
        force_rebuild=force_rebuild,
    )
    if resumed is not None:
        return resumed
    if not force_rebuild:
        linked = maybe_link_existing_prepared_outputs(spec, bench_root)
        if linked is not None:
            return linked
    split = spec.extra["split"]
    mic = spec.extra["mic"]
    _, manifests_dir = _ensure_alimeeting_manifests(bench_root, mic)
    recordings_path, supervisions_path = resolve_manifest_pair(manifests_dir, split, (mic,))
    cut_set = build_cutset_from_manifests(
        load_manifest(recordings_path),
        load_manifest(supervisions_path),
        spec.language,
        spec.dataset_id,
    )
    return write_cutset_and_compute_features(
        cut_set,
        spec.language,
        bench_root,
        spec.dataset_id,
        num_workers,
        batch_duration,
        device,
    )


def prepare_existing_cut_import(
    spec: DatasetSpec,
    bench_root: Path,
    num_workers: int,
    batch_duration: float,
    device: str,
    force_rebuild: bool = False,
) -> Path:
    resumed = maybe_resume_feature_outputs(
        spec.language,
        bench_root,
        spec.dataset_id,
        num_workers,
        batch_duration,
        device,
        force_rebuild=force_rebuild,
    )
    if resumed is not None:
        return resumed
    from lhotse import CutSet

    input_cuts = CutSet.from_file(_resolve_existing_cut(spec))
    cut_set = standardize_cutset(input_cuts, spec.language, spec.dataset_id)
    return write_cutset_and_compute_features(
        cut_set,
        spec.language,
        bench_root,
        spec.dataset_id,
        num_workers,
        batch_duration,
        device,
    )


def prepare_librispeech_eval(
    spec: DatasetSpec,
    bench_root: Path,
    num_workers: int,
    batch_duration: float,
    device: str,
    force_rebuild: bool = False,
) -> Path:
    resumed = maybe_resume_feature_outputs(
        spec.language,
        bench_root,
        spec.dataset_id,
        num_workers,
        batch_duration,
        device,
        force_rebuild=force_rebuild,
    )
    if resumed is not None:
        return resumed
    _, manifests_dir = _ensure_librispeech_manifests(bench_root)
    split = spec.extra["split"]
    recordings_path, supervisions_path = resolve_manifest_pair(manifests_dir, split)
    cut_set = build_cutset_from_manifests(
        load_manifest(recordings_path),
        load_manifest(supervisions_path),
        spec.language,
        spec.dataset_id,
    )
    return write_cutset_and_compute_features(
        cut_set,
        spec.language,
        bench_root,
        spec.dataset_id,
        num_workers,
        batch_duration,
        device,
    )


def prepare_tedlium_eval(
    spec: DatasetSpec,
    bench_root: Path,
    num_workers: int,
    batch_duration: float,
    device: str,
    force_rebuild: bool = False,
) -> Path:
    resumed = maybe_resume_feature_outputs(
        spec.language,
        bench_root,
        spec.dataset_id,
        num_workers,
        batch_duration,
        device,
        force_rebuild=force_rebuild,
    )
    if resumed is not None:
        return resumed
    _, manifests_dir = _ensure_tedlium_manifests(bench_root)
    split = spec.extra["split"]
    recordings_path, supervisions_path = resolve_manifest_pair(manifests_dir, split)
    cut_set = build_cutset_from_manifests(
        load_manifest(recordings_path),
        load_manifest(supervisions_path),
        spec.language,
        spec.dataset_id,
    )
    return write_cutset_and_compute_features(
        cut_set,
        spec.language,
        bench_root,
        spec.dataset_id,
        num_workers,
        batch_duration,
        device,
    )


def prepare_gigaspeech_eval(
    spec: DatasetSpec,
    bench_root: Path,
    num_workers: int,
    batch_duration: float,
    device: str,
    force_rebuild: bool = False,
) -> Path:
    resumed = maybe_resume_feature_outputs(
        spec.language,
        bench_root,
        spec.dataset_id,
        num_workers,
        batch_duration,
        device,
        force_rebuild=force_rebuild,
    )
    if resumed is not None:
        return resumed
    if not force_rebuild:
        linked = maybe_link_existing_gigaspeech_outputs(spec, bench_root)
        if linked is not None:
            return linked
    _, manifests_dir = _ensure_gigaspeech_manifests(bench_root)
    split = spec.extra["split"]
    recordings_path, supervisions_path = resolve_manifest_pair(manifests_dir, split)
    cut_set = build_cutset_from_manifests(
        load_manifest(recordings_path),
        load_manifest(supervisions_path),
        spec.language,
        spec.dataset_id,
    )
    return write_cutset_and_compute_features(
        cut_set,
        spec.language,
        bench_root,
        spec.dataset_id,
        num_workers,
        batch_duration,
        device,
    )


def prepare_voxpopuli_eval(
    spec: DatasetSpec,
    bench_root: Path,
    num_workers: int,
    batch_duration: float,
    device: str,
    force_rebuild: bool = False,
) -> Path:
    resumed = maybe_resume_feature_outputs(
        spec.language,
        bench_root,
        spec.dataset_id,
        num_workers,
        batch_duration,
        device,
        force_rebuild=force_rebuild,
    )
    if resumed is not None:
        return resumed
    _, manifests_dir = _ensure_voxpopuli_manifests(bench_root)
    split = spec.extra["split"]
    recordings_path, supervisions_path = resolve_manifest_pair(manifests_dir, split)
    cut_set = build_cutset_from_manifests(
        load_manifest(recordings_path),
        load_manifest(supervisions_path),
        spec.language,
        spec.dataset_id,
    )
    return write_cutset_and_compute_features(
        cut_set,
        spec.language,
        bench_root,
        spec.dataset_id,
        num_workers,
        batch_duration,
        device,
    )


def prepare_voxpopuli_accented_eval(
    spec: DatasetSpec,
    bench_root: Path,
    num_workers: int,
    batch_duration: float,
    device: str,
    force_rebuild: bool = False,
) -> Path:
    resumed = maybe_resume_feature_outputs(
        spec.language,
        bench_root,
        spec.dataset_id,
        num_workers,
        batch_duration,
        device,
        force_rebuild=force_rebuild,
    )
    if resumed is not None:
        return resumed
    recordings_path, supervisions_path = _ensure_voxpopuli_accented_test_manifests(
        bench_root
    )
    cut_set = build_cutset_from_manifests(
        load_manifest(recordings_path),
        load_manifest(supervisions_path),
        spec.language,
        spec.dataset_id,
    )
    cut_set = filter_accented_cutset(cut_set)
    return write_cutset_and_compute_features(
        cut_set,
        spec.language,
        bench_root,
        spec.dataset_id,
        num_workers,
        batch_duration,
        device,
    )


def prepare_commonvoice_eval(
    spec: DatasetSpec,
    bench_root: Path,
    num_workers: int,
    batch_duration: float,
    device: str,
    force_rebuild: bool = False,
) -> Path:
    resumed = maybe_resume_feature_outputs(
        spec.language,
        bench_root,
        spec.dataset_id,
        num_workers,
        batch_duration,
        device,
        force_rebuild=force_rebuild,
    )
    if resumed is not None:
        return resumed
    _, manifests_dir = _ensure_commonvoice_manifests(bench_root, spec.extra["release"])
    split = spec.extra["split"]
    recordings_path, supervisions_path = resolve_manifest_pair(manifests_dir, split)
    cut_set = build_cutset_from_manifests(
        load_manifest(recordings_path),
        load_manifest(supervisions_path),
        spec.language,
        spec.dataset_id,
    )
    return write_cutset_and_compute_features(
        cut_set,
        spec.language,
        bench_root,
        spec.dataset_id,
        num_workers,
        batch_duration,
        device,
    )


def prepare_aishell_eval(
    spec: DatasetSpec,
    bench_root: Path,
    num_workers: int,
    batch_duration: float,
    device: str,
    force_rebuild: bool = False,
) -> Path:
    resumed = maybe_resume_feature_outputs(
        spec.language,
        bench_root,
        spec.dataset_id,
        num_workers,
        batch_duration,
        device,
        force_rebuild=force_rebuild,
    )
    if resumed is not None:
        return resumed
    _, manifests_dir = _ensure_aishell_manifests(bench_root)
    split = spec.extra["split"]
    recordings_path, supervisions_path = resolve_manifest_pair(manifests_dir, split)
    cut_set = build_cutset_from_manifests(
        load_manifest(recordings_path),
        load_manifest(supervisions_path),
        spec.language,
        spec.dataset_id,
    )
    return write_cutset_and_compute_features(
        cut_set,
        spec.language,
        bench_root,
        spec.dataset_id,
        num_workers,
        batch_duration,
        device,
    )


def prepare_aishell2_eval(
    spec: DatasetSpec,
    bench_root: Path,
    num_workers: int,
    batch_duration: float,
    device: str,
    force_rebuild: bool = False,
) -> Path:
    resumed = maybe_resume_feature_outputs(
        spec.language,
        bench_root,
        spec.dataset_id,
        num_workers,
        batch_duration,
        device,
        force_rebuild=force_rebuild,
    )
    if resumed is not None:
        return resumed
    corpus_root = _resolve_aishell2_root()
    channel_root = _resolve_aishell2_channel_root(corpus_root, spec.extra["channel"])
    recordings, supervisions = _build_aishell2_subset_manifests(
        channel_root, spec.extra["split"], spec.language
    )
    cut_set = build_cutset_from_manifests(
        recordings,
        supervisions,
        spec.language,
        spec.dataset_id,
    )
    return write_cutset_and_compute_features(
        cut_set,
        spec.language,
        bench_root,
        spec.dataset_id,
        num_workers,
        batch_duration,
        device,
    )


PREPARERS = {
    "thchs30_clean": prepare_thchs30_clean,
    "thchs30_noise": prepare_thchs30_noise,
    "alimeeting_split": prepare_alimeeting_split,
    "existing_cut_import": prepare_existing_cut_import,
    "librispeech_eval": prepare_librispeech_eval,
    "tedlium_eval": prepare_tedlium_eval,
    "gigaspeech_eval": prepare_gigaspeech_eval,
    "voxpopuli_eval": prepare_voxpopuli_eval,
    "voxpopuli_accented_eval": prepare_voxpopuli_accented_eval,
    "commonvoice_eval": prepare_commonvoice_eval,
    "aishell_eval": prepare_aishell_eval,
    "aishell2_eval": prepare_aishell2_eval,
}


def main():
    args = get_parser().parse_args()
    mkdirs(args.bench_root)
    cleanup_legacy_metadata_tree(args.metadata_root)
    dataset_ids = resolve_dataset_ids(
        args.language,
        dataset_ids=parse_csv(args.test_sets),
        preset_names=parse_csv(args.test_set_preset),
    )
    registry_path = args.bench_root / "registry" / f"{args.language}_prepared.tsv"
    prepared: Dict[str, str] = load_existing_registry(registry_path)
    for spec in specs_for(args.language, dataset_ids):
        if spec.prep_kind not in PREPARERS:
            message = f"No preparer implemented for {spec.dataset_id} ({spec.prep_kind})"
            if args.skip_unavailable:
                write_unavailable_dataset_metadata(
                    spec, args.bench_root, message, metadata_root=args.metadata_root
                )
                logging.warning(message)
                continue
            raise ValueError(message)
        try:
            output = PREPARERS[spec.prep_kind](
                spec,
                args.bench_root,
                args.feature_num_workers,
                args.feature_batch_duration,
                args.feature_device,
                args.force_rebuild,
            )
            write_dataset_metadata(
                spec, args.bench_root, output, metadata_root=args.metadata_root
            )
            prepared[spec.dataset_id] = str(output)
            logging.info("Prepared %s -> %s", spec.dataset_id, output)
        except Exception as exc:
            if args.skip_unavailable:
                write_unavailable_dataset_metadata(
                    spec,
                    args.bench_root,
                    f"{type(exc).__name__}: {exc}",
                    metadata_root=args.metadata_root,
                )
                logging.exception("Skipping unavailable dataset %s", spec.dataset_id)
                continue
            raise

    with open(registry_path, "w", encoding="utf-8") as f:
        f.write("dataset_id\tcuts_path\n")
        for dataset_id, output in sorted(prepared.items()):
            f.write(f"{dataset_id}\t{output}\n")
    logging.info("Wrote preparation registry to %s", registry_path)


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s",
        level=logging.INFO,
    )
    main()
