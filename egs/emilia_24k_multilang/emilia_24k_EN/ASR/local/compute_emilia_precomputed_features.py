#!/usr/bin/env python3

import argparse
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Optional, Type

import numpy as np
import torch
from lhotse import CutSet, LilcomChunkyWriter, MonoCut, load_manifest, load_manifest_lazy
from lhotse.audio import AudioLoadingError, DurationMismatchError
from lhotse.cut.data import DataCut
from lhotse.cut.mixed import MixedCut
from lhotse.cut.padding import PaddingCut
from lhotse.dataset import SimpleCutSampler, UnsupervisedWaveformDataset
from lhotse.features.base import FeatureExtractor, Features
from lhotse.features.io import FeaturesWriter
from lhotse.qa import validate_features
from lhotse.utils import Pathlike, Seconds, fastcopy
from torch.utils.data import DataLoader
from tqdm.auto import tqdm

from f5tts_mel_extractor import F5TTSMelConfig, F5TTSMelExtractor


torch.set_num_threads(1)
torch.set_num_interop_threads(1)
torch.multiprocessing.set_sharing_strategy("file_system")


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


def get_args():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--raw-cuts-path", type=Path, required=True)
    parser.add_argument("--output-cuts-path", type=Path, required=True)
    parser.add_argument("--storage-path", type=str, required=True)
    parser.add_argument("--num-workers", type=int, default=20)
    parser.add_argument("--batch-duration", type=float, default=2000.0)
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
    parser.add_argument(
        "--sampling-rate",
        type=int,
        default=24000,
        help=(
            "Deprecated compatibility option. The current Emilia EN pipeline "
            "reads the true sampling rate from the cut manifests."
        ),
    )
    parser.add_argument(
        "--skip-missing-cuts",
        type=str,
        default="false",
        choices=["true", "false"],
        help="Skip any cuts missing after batch extraction and continue with the rest.",
    )
    parser.add_argument(
        "--bad-cut-report-dir",
        type=Path,
        default=None,
        help="Shared directory where per-shard bad cut reports are written.",
    )
    return parser.parse_args()


def shard_idx_from_output_path(path: Path) -> str:
    name = path.name
    prefix = "emilia_en_cuts_train."
    suffix = ".jsonl.gz"
    if name.startswith(prefix) and name.endswith(suffix):
        return name[len(prefix) : -len(suffix)]
    return path.stem


def report_path_for_output(output_cuts_path: Path, bad_cut_report_dir: Path) -> Path:
    return bad_cut_report_dir / f"shard-{shard_idx_from_output_path(output_cuts_path)}.jsonl"


def write_bad_cut_report(report_path: Path, records: List[Dict[str, Any]]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "w", encoding="utf-8", dir=report_path.parent, delete=False
    ) as f:
        temp_path = Path(f.name)
        for record in records:
            json.dump(record, f, ensure_ascii=True, sort_keys=True)
            f.write("\n")
    temp_path.replace(report_path)


def build_bad_cut_record(
    cut,
    raw_cuts_path: Optional[Path],
    output_cuts_path: Optional[Path],
) -> Dict[str, Any]:
    audio_source = None
    if cut.has_recording and cut.recording.sources:
        audio_source = cut.recording.sources[0].source

    reason_type = "MissingAfterBatch"
    reason_message = "Cut was missing from compute_and_store_features_batch output."
    try:
        cut.load_audio()
    except Exception as ex:  # noqa: BLE001
        reason_type = type(ex).__name__
        reason_message = str(ex)

    return {
        "audio_source": audio_source,
        "cut_id": cut.id,
        "declared_num_samples": cut.num_samples,
        "duration": cut.duration,
        "output_cuts_path": str(output_cuts_path) if output_cuts_path else None,
        "raw_cuts_path": str(raw_cuts_path) if raw_cuts_path else None,
        "reason_message": reason_message,
        "reason_type": reason_type,
        "recording_id": cut.recording_id,
        "sampling_rate": cut.sampling_rate,
        "start": cut.start,
    }


def maybe_write_bad_cut_report(
    records: List[Dict[str, Any]],
    output_cuts_path: Optional[Path],
    bad_cut_report_dir: Optional[Path],
) -> None:
    if bad_cut_report_dir is None or output_cuts_path is None:
        return

    report_path = report_path_for_output(output_cuts_path, bad_cut_report_dir)
    if records:
        write_bad_cut_report(report_path, records)
    elif report_path.exists():
        report_path.unlink()


def ensure_storage_index_exists(storage_index: Path) -> None:
    storage_index.parent.mkdir(parents=True, exist_ok=True)
    storage_index.touch()


def compute_and_store_features_batch_checked(
    cut_set: CutSet,
    extractor: FeatureExtractor,
    storage_path: Pathlike,
    batch_duration: Seconds,
    num_workers: int,
    storage_type: Type[FeaturesWriter],
    overwrite: bool,
) -> CutSet:
    frame_shift = extractor.frame_shift
    feature_sampling_rate = getattr(
        extractor, "feature_sampling_rate", None
    ) or getattr(extractor, "sampling_rate", None)

    if feature_sampling_rate is None:
        raise RuntimeError(
            f"{type(extractor).__name__} must expose feature_sampling_rate when "
            "using the checked batch writer."
        )

    cuts_writer = CutSet.open_writer(None, overwrite=overwrite)
    sampler = SimpleCutSampler(cut_set, max_duration=batch_duration)
    dataset = UnsupervisedWaveformDataset(collate=False)
    dloader = DataLoader(
        dataset, batch_size=None, sampler=sampler, num_workers=num_workers
    )

    def _save_worker(cuts, features: List[np.ndarray]) -> None:
        for cut, feat_mat in zip(cuts, features):
            if isinstance(cut, PaddingCut):
                cuts_writer.write(
                    fastcopy(
                        cut,
                        num_frames=feat_mat.shape[0],
                        num_features=feat_mat.shape[1],
                        frame_shift=frame_shift,
                    )
                )
                continue

            if isinstance(feat_mat, torch.Tensor):
                feat_mat = feat_mat.cpu().numpy()
            storage_key = feats_writer.write(cut.id, feat_mat)
            feat_manifest = Features(
                start=cut.start,
                duration=cut.duration,
                type=extractor.name,
                num_frames=feat_mat.shape[0],
                num_features=feat_mat.shape[1],
                frame_shift=frame_shift,
                sampling_rate=feature_sampling_rate,
                channels=cut.channel,
                storage_type=feats_writer.name,
                storage_path=str(feats_writer.storage_path),
                storage_key=storage_key,
            )
            validate_features(feat_manifest, feats_data=feat_mat)

            if isinstance(cut, DataCut):
                feat_manifest.recording_id = cut.recording_id
                cut = fastcopy(cut, features=feat_manifest)
            if isinstance(cut, MixedCut):
                feat_manifest.recording_id = cut.id
                cut = MonoCut(
                    id=cut.id,
                    start=0,
                    duration=cut.duration,
                    channel=0,
                    supervisions=[
                        fastcopy(s, recording_id=cut.id, channel=0)
                        for s in cut.supervisions
                    ],
                    features=feat_manifest,
                    recording=None,
                )
            cuts_writer.write(cut, flush=True)

    futures = []
    with cuts_writer, storage_type(
        storage_path, mode="w" if overwrite else "a"
    ) as feats_writer, tqdm(
        desc="Computing features in batches", total=sampler.num_cuts
    ) as progress, ThreadPoolExecutor(
        max_workers=1
    ) as executor:
        for batch in dloader:
            cuts = batch["cuts"]
            waves = batch["audio"]
            if len(cuts) == 0:
                continue
            assert all(c.sampling_rate == cuts[0].sampling_rate for c in cuts)

            with torch.no_grad():
                features = extractor.extract_batch(
                    waves, sampling_rate=cuts[0].sampling_rate, lengths=None
                )

            futures.append(executor.submit(_save_worker, cuts, features))
            progress.update(len(cuts))

    for future in futures:
        try:
            future.result()
        except Exception as ex:
            raise RuntimeError(
                "Feature save worker failed while writing checked batch features: "
                f"storage_path={storage_path} batch_duration={batch_duration} "
                f"num_workers={num_workers}"
            ) from ex

    return cuts_writer.open_manifest()


def compute_features_grouped_by_sampling_rate(
    cut_set: CutSet,
    extractor: F5TTSMelExtractor,
    storage_path: str,
    num_workers: int,
    batch_duration: float,
    skip_missing_cuts: bool = False,
    raw_cuts_path: Optional[Path] = None,
    output_cuts_path: Optional[Path] = None,
    bad_cut_report_dir: Optional[Path] = None,
) -> CutSet:
    cuts = list(cut_set)
    if not cuts:
        return CutSet.from_cuts([])

    cuts_by_sampling_rate = defaultdict(list)
    for cut in cuts:
        cuts_by_sampling_rate[cut.sampling_rate].append(cut)

    computed_by_id = {}
    overwrite = True
    for sampling_rate_batch_idx, sampling_rate in enumerate(
        sorted(cuts_by_sampling_rate)
    ):
        rate_cuts = cuts_by_sampling_rate[sampling_rate]
        logging.info(
            "Computing features for %s cuts at sampling_rate=%s (overwrite=%s)",
            len(rate_cuts),
            sampling_rate,
            overwrite,
        )
        grouped_cut_set = CutSet.from_cuts(rate_cuts)
        computed = compute_and_store_features_batch_checked(
            cut_set=grouped_cut_set,
            extractor=extractor,
            storage_path=storage_path,
            batch_duration=batch_duration,
            num_workers=num_workers,
            storage_type=LilcomChunkyWriter,
            overwrite=overwrite,
        )
        if computed is None:
            shard_idx = (
                shard_idx_from_output_path(output_cuts_path)
                if output_cuts_path is not None
                else None
            )
            raise RuntimeError(
                "compute_and_store_features_batch returned None for "
                f"shard={shard_idx} sampling_rate_batch_idx={sampling_rate_batch_idx} "
                f"sampling_rate={sampling_rate} batch_duration={batch_duration} "
                f"num_workers={num_workers} num_cuts={len(rate_cuts)} "
                f"first_cut_id={rate_cuts[0].id} last_cut_id={rate_cuts[-1].id} "
                f"storage_path={storage_path} raw_cuts_path={raw_cuts_path} "
                f"output_cuts_path={output_cuts_path}"
            )
        for computed_cut in computed:
            computed_by_id[computed_cut.id] = computed_cut
        overwrite = False

    missing_ids = [cut.id for cut in cuts if cut.id not in computed_by_id]
    if missing_ids:
        if skip_missing_cuts:
            missing_id_set = set(missing_ids)
            bad_cut_records = [
                build_bad_cut_record(
                    cut=cut,
                    raw_cuts_path=raw_cuts_path,
                    output_cuts_path=output_cuts_path,
                )
                for cut in cuts
                if cut.id in missing_id_set
            ]
            audio_error_count = sum(
                record["reason_type"] in {"AudioLoadingError", "DurationMismatchError"}
                for record in bad_cut_records
            )
            other_error_count = len(bad_cut_records) - audio_error_count
            maybe_write_bad_cut_report(
                records=bad_cut_records,
                output_cuts_path=output_cuts_path,
                bad_cut_report_dir=bad_cut_report_dir,
            )
            logging.warning(
                "Skipping %s missing cuts for %s; audio_related=%s other=%s first=%s",
                len(missing_ids),
                output_cuts_path if output_cuts_path is not None else storage_path,
                audio_error_count,
                other_error_count,
                missing_ids[0],
            )
            return CutSet.from_cuts(
                computed_by_id[cut.id] for cut in cuts if cut.id in computed_by_id
            )
        raise RuntimeError(
            f"Missing computed cuts for {len(missing_ids)} ids; first missing id: {missing_ids[0]}"
        )

    maybe_write_bad_cut_report(
        records=[],
        output_cuts_path=output_cuts_path,
        bad_cut_report_dir=bad_cut_report_dir,
    )
    return CutSet.from_cuts(computed_by_id[cut.id] for cut in cuts)


def main():
    args = get_args()
    if args.output_cuts_path.is_file():
        logging.info("%s exists - skipping", args.output_cuts_path)
        return

    if args.device == "auto":
        device = (
            torch.device("cuda", 0)
            if torch.cuda.is_available()
            else torch.device("cpu")
        )
    elif args.device == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("--device cuda was requested but CUDA is not available")
        device = torch.device("cuda", 0)
    else:
        device = torch.device("cpu")
    extractor = F5TTSMelExtractor(
        F5TTSMelConfig(target_sample_rate=24000, n_mels=100, device=str(device))
    )
    logging.info(
        "device: %s, target_sampling_rate: 24000; using cut manifest audio metadata",
        device,
    )

    storage_index = Path(f"{args.storage_path}.lca")
    if storage_index.exists():
        os.remove(storage_index)

    cut_set = load_cutset(args.raw_cuts_path)
    cut_set = compute_features_grouped_by_sampling_rate(
        cut_set=cut_set,
        extractor=extractor,
        storage_path=args.storage_path,
        num_workers=args.num_workers,
        batch_duration=args.batch_duration,
        skip_missing_cuts=args.skip_missing_cuts == "true",
        raw_cuts_path=args.raw_cuts_path,
        output_cuts_path=args.output_cuts_path,
        bad_cut_report_dir=args.bad_cut_report_dir,
    )

    cut_set = cut_set.trim_to_supervisions(keep_overlapping=False, min_duration=None)
    cut_set.to_file(args.output_cuts_path)
    ensure_storage_index_exists(storage_index)
    logging.info("Saved computed cuts to %s", args.output_cuts_path)


if __name__ == "__main__":
    formatter = "%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s"
    logging.basicConfig(format=formatter, level=logging.INFO)
    main()
