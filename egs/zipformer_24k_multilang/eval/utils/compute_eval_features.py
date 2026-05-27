#!/usr/bin/env python3

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import torch
import torchaudio
from lhotse import CutSet, load_manifest, load_manifest_lazy
from lhotse.utils import compute_num_frames, compute_num_samples, fastcopy


def _resolve_recipe_local_root(language: str) -> Path:
    eval_root = Path(__file__).resolve().parents[1]
    recipe_root = eval_root.parent / f"zipformer_24k_{language.lower()}" / "ASR" / "local"
    if not recipe_root.is_dir():
        raise FileNotFoundError(f"Missing recipe local dir for language={language}: {recipe_root}")
    return recipe_root


def _import_feature_extractor(language: str):
    recipe_local_root = _resolve_recipe_local_root(language)
    if str(recipe_local_root) not in sys.path:
        sys.path.insert(0, str(recipe_local_root))

    from f5tts_mel_extractor import F5TTSMelConfig, F5TTSMelExtractor

    return F5TTSMelConfig, F5TTSMelExtractor


torch.set_num_threads(1)
torch.set_num_interop_threads(1)
torch.multiprocessing.set_sharing_strategy("file_system")


@dataclass(frozen=True)
class TrueAudioInfo:
    sampling_rate: int
    num_samples: int

    @property
    def duration(self) -> float:
        return round(self.num_samples / self.sampling_rate, ndigits=12)


def load_cutset(path: Path) -> CutSet:
    cut_set = CutSet.from_file(path)
    if cut_set is not None:
        return cut_set

    cut_set = load_manifest_lazy(path)
    if cut_set is not None:
        return cut_set

    cut_set = load_manifest(path)
    if cut_set is not None:
        return cut_set

    raise ValueError(f"Unable to load cut set from {path}")


def validate_trimmed_cutset(cut_set: CutSet, source_path: Path) -> None:
    seen_ids = set()
    for cut in cut_set:
        if cut.id in seen_ids:
            raise ValueError(f"Duplicate cut id detected in {source_path}: {cut.id}")
        seen_ids.add(cut.id)

        if cut.duration <= 0:
            raise ValueError(f"Non-positive cut duration in {source_path}: {cut.id}")

        if len(cut.supervisions) != 1:
            raise ValueError(
                f"Eval feature writer expects exactly one supervision per cut: "
                f"{cut.id} has {len(cut.supervisions)}"
            )

        supervision = cut.supervisions[0]
        if abs(supervision.start) > 1.0e-6:
            raise ValueError(
                f"Eval feature writer expects supervision to start at 0.0 after trim: "
                f"{cut.id} starts at {supervision.start}"
            )
        if abs(supervision.duration - cut.duration) > 1.0e-6:
            raise ValueError(
                f"Eval feature writer expects cut/supervision durations to match: "
                f"{cut.id} cut={cut.duration} supervision={supervision.duration}"
            )


def validate_feature_attachment(cut_set: CutSet, source_path: Path) -> None:
    missing = [cut.id for cut in cut_set if not cut.has_features]
    if missing:
        preview = ", ".join(missing[:10])
        raise ValueError(
            f"Feature attachment failed for {source_path}: "
            f"{len(missing)} cuts are missing features; first ids: {preview}"
        )


def resolve_recording_source_path(cut) -> Path:
    if not cut.has_recording:
        raise ValueError(f"Cut is missing recording metadata: {cut.id}")

    if len(cut.recording.sources) != 1:
        raise ValueError(
            f"Eval feature writer expects exactly one recording source per cut: "
            f"{cut.id} has {len(cut.recording.sources)}"
        )

    source = cut.recording.sources[0]
    if source.type != "file":
        raise ValueError(
            f"Eval feature writer only supports file-backed recordings: "
            f"{cut.id} has source type {source.type}"
        )

    return Path(source.source).expanduser().resolve()


def read_true_audio_info(source_path: Path) -> TrueAudioInfo:
    waveform, sampling_rate = torchaudio.load(str(source_path))
    if waveform.ndim != 2 or waveform.shape[-1] <= 0:
        raise ValueError(
            f"Unable to decode non-empty waveform from {source_path}: "
            f"shape={tuple(waveform.shape)}"
        )
    return TrueAudioInfo(
        sampling_rate=int(sampling_rate),
        num_samples=int(waveform.shape[-1]),
    )


def normalize_cutset_to_true_audio_metadata(
    cut_set: CutSet, source_path: Path
) -> CutSet:
    audio_info_cache = {}
    normalized_cuts = []
    corrected_recording_sources = set()
    corrected_cuts = 0

    for cut in cut_set:
        recording_source = resolve_recording_source_path(cut)
        cache_key = str(recording_source)
        if cache_key not in audio_info_cache:
            audio_info_cache[cache_key] = read_true_audio_info(recording_source)
        true_audio = audio_info_cache[cache_key]

        recording = cut.recording
        normalized_recording = recording
        if (
            recording.sampling_rate != true_audio.sampling_rate
            or recording.num_samples != true_audio.num_samples
            or abs(recording.duration - true_audio.duration) > 1.0e-6
        ):
            normalized_recording = fastcopy(
                recording,
                sampling_rate=true_audio.sampling_rate,
                num_samples=true_audio.num_samples,
                duration=true_audio.duration,
            )
            corrected_recording_sources.add(cache_key)

        start_sample = compute_num_samples(cut.start, true_audio.sampling_rate)
        available_num_samples = max(true_audio.num_samples - start_sample, 0)
        cut_num_samples = min(
            compute_num_samples(cut.duration, true_audio.sampling_rate),
            available_num_samples,
        )
        cut_duration = round(cut_num_samples / true_audio.sampling_rate, ndigits=12)

        normalized_supervisions = cut.supervisions
        if len(cut.supervisions) == 1 and abs(cut.supervisions[0].duration - cut_duration) > 1.0e-6:
            normalized_supervisions = [
                fastcopy(cut.supervisions[0], duration=cut_duration)
            ]

        normalized_cut = cut
        if (
            cut.recording is not normalized_recording
            or abs(cut.duration - cut_duration) > 1.0e-6
            or normalized_supervisions is not cut.supervisions
        ):
            normalized_cut = fastcopy(
                cut,
                recording=normalized_recording,
                duration=cut_duration,
                supervisions=normalized_supervisions,
                features=None,
            )
            corrected_cuts += 1

        normalized_cuts.append(normalized_cut)

    logging.info(
        "Normalized true-audio metadata for %s cuts from %s; corrected_recordings=%s corrected_cuts=%s unique_sources=%s",
        len(normalized_cuts),
        source_path,
        len(corrected_recording_sources),
        corrected_cuts,
        len(audio_info_cache),
    )
    return CutSet.from_cuts(normalized_cuts)


def filter_zero_frame_cuts(
    cut_set: CutSet, frame_shift: float, source_path: Path
) -> CutSet:
    kept = []
    dropped = []
    for cut in cut_set:
        expected_num_frames = compute_num_frames(
            duration=cut.duration,
            frame_shift=frame_shift,
            sampling_rate=cut.sampling_rate,
        )
        if expected_num_frames <= 0 or cut.num_samples <= 0 or cut.duration <= 0:
            dropped.append(cut.id)
            continue
        kept.append(cut)

    if dropped:
        logging.warning(
            "Dropped %s zero-frame/invalid cuts from %s; first ids: %s",
            len(dropped),
            source_path,
            ", ".join(dropped[:10]),
        )

    return CutSet.from_cuts(kept)


def align_cutset_to_feature_durations(
    cut_set: CutSet, source_path: Path, tolerance: float = 1.0e-3
) -> CutSet:
    aligned = []
    repaired = 0

    for cut in cut_set:
        features = getattr(cut, "features", None)
        if features is None or len(cut.supervisions) != 1:
            aligned.append(cut)
            continue

        target_duration = float(getattr(features, "duration", 0.0) or 0.0)
        if target_duration <= 0.0:
            aligned.append(cut)
            continue

        supervision = cut.supervisions[0]
        if abs(supervision.start) > 1.0e-6:
            aligned.append(cut)
            continue

        if (
            abs(cut.duration - target_duration) <= 1.0e-6
            and abs(supervision.duration - target_duration) <= 1.0e-6
        ):
            aligned.append(cut)
            continue

        if (
            abs(cut.duration - target_duration) <= tolerance
            and abs(supervision.duration - target_duration) <= tolerance
        ):
            aligned.append(
                fastcopy(
                    cut,
                    duration=target_duration,
                    supervisions=[fastcopy(supervision, duration=target_duration)],
                )
            )
            repaired += 1
            continue

        aligned.append(cut)

    if repaired:
        logging.info(
            "Aligned %s cut/supervision durations to extracted feature durations for %s",
            repaired,
            source_path,
        )

    return CutSet.from_cuts(aligned)


def get_args():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--raw-cuts-path", type=Path, required=True)
    parser.add_argument("--output-cuts-path", type=Path, required=True)
    parser.add_argument("--storage-path", type=str, required=True)
    parser.add_argument("--language", type=str, required=True, choices=["zh", "en"])
    parser.add_argument("--num-workers", type=int, default=20)
    parser.add_argument("--batch-duration", type=float, default=1000.0)
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        choices=["auto", "cpu", "cuda"],
        help=(
            "Feature extraction device. 'auto' uses CUDA when available, "
            "otherwise CPU."
        ),
    )
    return parser.parse_args()


def resolve_device(device_name: str) -> torch.device:
    if device_name == "auto":
        return (
            torch.device("cuda", 0)
            if torch.cuda.is_available()
            else torch.device("cpu")
        )

    if device_name == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("--device cuda was requested but CUDA is not available")
        return torch.device("cuda", 0)

    return torch.device("cpu")


def main():
    args = get_args()
    if args.output_cuts_path.is_file():
        logging.info("%s exists - skipping", args.output_cuts_path)
        return

    F5TTSMelConfig, F5TTSMelExtractor = _import_feature_extractor(args.language)
    device = resolve_device(args.device)
    extractor = F5TTSMelExtractor(
        F5TTSMelConfig(target_sample_rate=24000, n_mels=100, device=str(device))
    )
    logging.info("device: %s target_sampling_rate: 24000", device)

    storage_index = Path(f"{args.storage_path}.lca")
    if storage_index.exists():
        os.remove(storage_index)

    cut_set = load_cutset(args.raw_cuts_path)
    cut_set = normalize_cutset_to_true_audio_metadata(cut_set, args.raw_cuts_path)
    cut_set = cut_set.resample(24000)
    cut_set = filter_zero_frame_cuts(
        cut_set, frame_shift=extractor.frame_shift, source_path=args.raw_cuts_path
    )
    if len(cut_set) == 0:
        raise ValueError(f"All cuts became invalid after resample: {args.raw_cuts_path}")
    validate_trimmed_cutset(cut_set, args.raw_cuts_path)

    computed = cut_set.compute_and_store_features(
        extractor=extractor,
        storage_path=args.storage_path,
        num_jobs=args.num_workers,
    )

    if computed is None:
        raise ValueError(
            f"Feature extraction did not return a cut manifest: {args.raw_cuts_path}"
        )

    cut_set = align_cutset_to_feature_durations(computed, args.raw_cuts_path)
    args.output_cuts_path.parent.mkdir(parents=True, exist_ok=True)
    cut_set.to_file(args.output_cuts_path)

    validate_trimmed_cutset(cut_set, args.output_cuts_path)
    validate_feature_attachment(cut_set, args.output_cuts_path)
    logging.info("Saved computed cuts to %s", args.output_cuts_path)


if __name__ == "__main__":
    formatter = "%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s"
    logging.basicConfig(format=formatter, level=logging.INFO)
    main()
