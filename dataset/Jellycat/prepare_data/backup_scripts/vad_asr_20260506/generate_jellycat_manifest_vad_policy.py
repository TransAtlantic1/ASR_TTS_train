#!/usr/bin/env python3

import argparse
import gzip
import json
import math
import sys
from contextlib import ExitStack, nullcontext
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

import numpy as np
import soundfile as sf


DEFAULT_JELLYCAT_ROOT = Path(
    "/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat"
)
DEFAULT_SILERO_REPO = Path(__file__).resolve().parent / "external" / "silero-vad"


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description=(
            "Generate manifest-only Jellycat reject/split artifacts for the "
            "duration60+vad30 cleanup policy. This script reads existing FLACs "
            "for VAD but does not write or modify audio files."
        ),
    )
    parser.add_argument("--language", required=True, help="Target language, e.g. ZH.")
    parser.add_argument(
        "--segment-manifest",
        type=Path,
        required=True,
        help="Input Jellycat segment manifest JSONL/JSONL.GZ.",
    )
    parser.add_argument(
        "--audio-root",
        type=Path,
        default=DEFAULT_JELLYCAT_ROOT,
        help="Root used to resolve relative segment wav paths.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Output directory. Default: "
            "<audio-root>/manifests/<LANG>/duration60_vad30_manifest_only_v1"
        ),
    )
    parser.add_argument(
        "--policy-name",
        default="duration60_vad30_manifest_only_v1",
        help="Policy/version name embedded in output filenames and records.",
    )
    parser.add_argument(
        "--vad-min-duration",
        type=float,
        default=30.0,
        help="Utterances longer than this and <= direct threshold enter VAD.",
    )
    parser.add_argument(
        "--direct-reject-duration",
        type=float,
        default=60.0,
        help="Utterances longer than this are rejected without VAD.",
    )
    parser.add_argument(
        "--max-child-duration",
        type=float,
        default=30.0,
        help="VAD children longer than this are rejected.",
    )
    parser.add_argument(
        "--classify-only",
        action="store_true",
        help=(
            "Only generate parent direct rejects and optional VAD candidates; "
            "do not read audio or produce post-VAD child rejects/split maps."
        ),
    )
    parser.add_argument(
        "--vad-backend",
        choices=["silero", "energy"],
        default="silero",
        help="VAD backend used for 30-60s utterances when not classify-only.",
    )
    parser.add_argument(
        "--silero-repo",
        type=Path,
        default=DEFAULT_SILERO_REPO,
        help="Path to a Silero VAD source checkout containing src/silero_vad.",
    )
    parser.add_argument("--silero-threshold", type=float, default=0.5)
    parser.add_argument(
        "--silero-sampling-rate",
        type=int,
        default=16000,
        help="Sampling rate passed to Silero; 24k Jellycat audio is resampled.",
    )
    parser.add_argument(
        "--silero-min-silence-ms",
        type=int,
        default=350,
        help="Silero min_silence_duration_ms.",
    )
    parser.add_argument(
        "--silero-speech-pad-ms",
        type=int,
        default=100,
        help="Silero speech_pad_ms.",
    )
    parser.add_argument(
        "--silero-max-speech-duration",
        type=float,
        default=0.0,
        help=(
            "Silero max_speech_duration_s. <=0 keeps natural spans and lets "
            "the post-VAD >30s rule reject long children."
        ),
    )
    parser.add_argument(
        "--write-vad-candidates",
        action="store_true",
        help="Write 30-60s VAD candidate audit JSONL.",
    )
    parser.add_argument(
        "--write-manifest-preview",
        action="store_true",
        help=(
            "Write a manifest-only cleaned segment preview. Child wav paths are "
            "planned paths and audio_write_pending=true until audio is actually cut."
        ),
    )
    parser.add_argument(
        "--no-write-annotation-segments",
        action="store_true",
        help=(
            "Do not write the flat VAD child annotation JSONL. By default this "
            "is written for downstream ASR/text annotation."
        ),
    )
    parser.add_argument(
        "--text-split-mode",
        choices=["empty", "parent"],
        default="empty",
        help=(
            "How to populate child text. Default leaves child text empty because "
            "VAD does not provide reliable text boundaries; parent_text is kept "
            "for later annotation."
        ),
    )
    parser.add_argument("--frame-ms", type=float, default=30.0)
    parser.add_argument("--hop-ms", type=float, default=10.0)
    parser.add_argument("--abs-threshold-db", type=float, default=-50.0)
    parser.add_argument("--noise-percentile", type=float, default=20.0)
    parser.add_argument("--noise-margin-db", type=float, default=8.0)
    parser.add_argument(
        "--max-threshold-db",
        type=float,
        default=-25.0,
        help="Upper cap for adaptive energy threshold.",
    )
    parser.add_argument(
        "--merge-silence-sec",
        type=float,
        default=0.35,
        help="Merge adjacent speech spans separated by at most this silence.",
    )
    parser.add_argument("--min-speech-sec", type=float, default=0.25)
    parser.add_argument("--pad-sec", type=float, default=0.10)
    parser.add_argument(
        "--max-records",
        type=int,
        default=-1,
        help="Optional cap on records seen after sharding, for smoke tests.",
    )
    parser.add_argument(
        "--num-shards",
        type=int,
        default=1,
        help="Modulo shard count for large VAD runs.",
    )
    parser.add_argument(
        "--shard-index",
        type=int,
        default=0,
        help="Modulo shard index in [0, num_shards).",
    )
    parser.add_argument("--progress-interval", type=int, default=100000)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting existing output files.",
    )
    return parser.parse_args()


def open_text(path: Path, mode: str):
    if path.suffix == ".gz":
        return gzip.open(path, mode, encoding="utf-8")
    return path.open(mode, encoding="utf-8")


def iter_jsonl(path: Path) -> Iterator[dict]:
    with open_text(path, "rt") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


class JsonlWriter:
    def __init__(self, path: Path, overwrite: bool) -> None:
        self.path = path
        self.overwrite = overwrite
        self.handle = None

    def __enter__(self):
        if self.path.exists() and not self.overwrite:
            raise FileExistsError(f"{self.path} exists; pass --overwrite")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open_text(self.path, "wt")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.handle is not None:
            self.handle.close()

    def write(self, record: dict) -> None:
        assert self.handle is not None
        self.handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def format_threshold(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return str(value).replace(".", "p")


def output_paths(output_dir: Path, language: str, policy_name: str) -> Dict[str, Path]:
    prefix = f"jellycat_{language}_{policy_name}"
    return {
        "parent_reject": output_dir / f"{prefix}.parent_reject.jsonl",
        "child_reject": output_dir / f"{prefix}.child_reject.post_vad_duration_gt_30s.jsonl",
        "all_reject": output_dir / f"{prefix}.all_reject.jsonl",
        "split_map": output_dir / f"{prefix}.vad_split_map.jsonl",
        "annotation_segments": output_dir / f"{prefix}.vad_annotation_segments.jsonl",
        "vad_candidates": output_dir / f"{prefix}.vad_candidates.duration_gt_30s_le_60s.jsonl",
        "manifest_preview": output_dir / f"{prefix}.segments.manifest_only.jsonl.gz",
        "summary": output_dir / f"{prefix}.summary.json",
    }


def resolve_audio_path(audio_root: Path, wav: str, language: str) -> Path:
    wav_path = Path(wav)
    if wav_path.is_absolute():
        return wav_path
    candidates = [audio_root / wav_path]
    parts = wav_path.parts
    if parts and parts[0] == language:
        candidates.append(audio_root / Path(*parts[1:]))
    else:
        candidates.append(audio_root / language / wav_path)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def planned_child_wav(parent_wav: str, child_id: str) -> str:
    path = Path(parent_wav)
    suffix = path.suffix or ".flac"
    return str(path.with_name(f"{child_id}{suffix}"))


def safe_float(value, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def read_audio(path: Path) -> Tuple[np.ndarray, int]:
    audio, sample_rate = sf.read(path, dtype="float32", always_2d=False)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    return np.asarray(audio, dtype=np.float32), int(sample_rate)


def frame_rms_db(audio: np.ndarray, sample_rate: int, frame_ms: float, hop_ms: float) -> Tuple[np.ndarray, np.ndarray]:
    frame_len = max(1, int(round(sample_rate * frame_ms / 1000.0)))
    hop_len = max(1, int(round(sample_rate * hop_ms / 1000.0)))
    if audio.size <= frame_len:
        rms = math.sqrt(float(np.mean(np.square(audio, dtype=np.float64)))) if audio.size else 0.0
        return np.array([0], dtype=np.int64), np.array([20.0 * math.log10(rms + 1e-12)])

    starts = np.arange(0, audio.size - frame_len + 1, hop_len, dtype=np.int64)
    squared = np.square(audio.astype(np.float64, copy=False))
    cumsum = np.concatenate(([0.0], np.cumsum(squared)))
    energy = (cumsum[starts + frame_len] - cumsum[starts]) / float(frame_len)
    rms = np.sqrt(np.maximum(energy, 0.0))
    db = 20.0 * np.log10(rms + 1e-12)
    return starts, db


def merge_spans(spans: Sequence[Tuple[float, float]], merge_silence_sec: float) -> List[Tuple[float, float]]:
    merged: List[Tuple[float, float]] = []
    for start, end in spans:
        if not merged or start - merged[-1][1] > merge_silence_sec:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def energy_vad_spans(audio: np.ndarray, sample_rate: int, args: argparse.Namespace) -> Tuple[List[Tuple[float, float]], Dict]:
    total_duration = audio.size / float(sample_rate) if sample_rate else 0.0
    starts, db = frame_rms_db(audio, sample_rate, args.frame_ms, args.hop_ms)
    if db.size == 0:
        return [], {"backend": "energy", "threshold_db": None, "max_db": None, "total_duration": total_duration}

    noise_db = float(np.percentile(db, args.noise_percentile))
    threshold_db = max(
        args.abs_threshold_db,
        min(noise_db + args.noise_margin_db, args.max_threshold_db),
    )
    speech_mask = db >= threshold_db
    raw_spans: List[Tuple[float, float]] = []
    frame_len_sec = args.frame_ms / 1000.0

    in_span = False
    span_start = 0.0
    last_end = 0.0
    for start_sample, is_speech in zip(starts, speech_mask):
        start = float(start_sample) / sample_rate
        end = min(total_duration, start + frame_len_sec)
        if is_speech and not in_span:
            span_start = start
            in_span = True
        if is_speech:
            last_end = end
        if in_span and not is_speech:
            raw_spans.append((span_start, last_end))
            in_span = False
    if in_span:
        raw_spans.append((span_start, last_end))

    padded = [
        (max(0.0, start - args.pad_sec), min(total_duration, end + args.pad_sec))
        for start, end in raw_spans
    ]
    merged = merge_spans(padded, args.merge_silence_sec)
    spans = [
        (start, end)
        for start, end in merged
        if end - start >= args.min_speech_sec
    ]
    return spans, {
        "backend": "energy",
        "threshold_db": threshold_db,
        "noise_db": noise_db,
        "max_db": float(np.max(db)),
        "speech_frame_ratio": float(np.mean(speech_mask)),
        "total_duration": total_duration,
    }


def load_silero_backend(args: argparse.Namespace) -> Optional[Dict]:
    if args.classify_only or args.vad_backend != "silero":
        return None
    silero_src = args.silero_repo / "src"
    if not (silero_src / "silero_vad").is_dir():
        raise FileNotFoundError(
            f"Missing Silero VAD source package under {silero_src}; "
            "set --silero-repo to a checkout of https://github.com/snakers4/silero-vad"
        )
    sys.path.insert(0, str(silero_src))
    import torch
    import torchaudio
    from silero_vad import get_speech_timestamps, load_silero_vad

    model = load_silero_vad(onnx=False)
    return {
        "torch": torch,
        "torchaudio": torchaudio,
        "model": model,
        "get_speech_timestamps": get_speech_timestamps,
    }


def silero_vad_spans(
    audio: np.ndarray,
    sample_rate: int,
    args: argparse.Namespace,
    state: Dict,
) -> Tuple[List[Tuple[float, float]], Dict]:
    torch = state["torch"]
    torchaudio = state["torchaudio"]
    wav = torch.from_numpy(audio.astype(np.float32, copy=False))
    target_sr = int(args.silero_sampling_rate)
    if sample_rate != target_sr:
        wav = torchaudio.functional.resample(
            wav.unsqueeze(0),
            orig_freq=int(sample_rate),
            new_freq=target_sr,
        ).squeeze(0)
    timestamps = state["get_speech_timestamps"](
        wav,
        state["model"],
        threshold=float(args.silero_threshold),
        sampling_rate=target_sr,
        min_speech_duration_ms=int(round(args.min_speech_sec * 1000.0)),
        min_silence_duration_ms=int(args.silero_min_silence_ms),
        speech_pad_ms=int(args.silero_speech_pad_ms),
        max_speech_duration_s=(
            float("inf")
            if args.silero_max_speech_duration <= 0
            else float(args.silero_max_speech_duration)
        ),
        return_seconds=True,
    )
    total_duration = audio.size / float(sample_rate) if sample_rate else 0.0
    spans = [
        (
            max(0.0, float(item["start"])),
            min(total_duration, float(item["end"])),
        )
        for item in timestamps
        if float(item["end"]) > float(item["start"])
    ]
    return spans, {
        "backend": "silero",
        "silero_repo": str(args.silero_repo),
        "threshold": float(args.silero_threshold),
        "original_sampling_rate": int(sample_rate),
        "silero_sampling_rate": target_sr,
        "min_speech_duration_ms": int(round(args.min_speech_sec * 1000.0)),
        "min_silence_duration_ms": int(args.silero_min_silence_ms),
        "speech_pad_ms": int(args.silero_speech_pad_ms),
        "max_speech_duration_s": (
            None
            if args.silero_max_speech_duration <= 0
            else float(args.silero_max_speech_duration)
        ),
        "total_duration": total_duration,
        "num_spans": len(spans),
    }


def run_vad(
    audio: np.ndarray,
    sample_rate: int,
    args: argparse.Namespace,
    silero_state: Optional[Dict],
) -> Tuple[List[Tuple[float, float]], Dict]:
    if args.vad_backend == "silero":
        if silero_state is None:
            raise RuntimeError("Silero backend was not loaded")
        return silero_vad_spans(audio, sample_rate, args, silero_state)
    return energy_vad_spans(audio, sample_rate, args)


def split_text_by_duration(
    text: str, spans: Sequence[Tuple[float, float]], mode: str
) -> Tuple[List[str], str]:
    if not spans:
        return [], mode
    if mode == "parent":
        return [text for _ in spans], "parent_repeated"
    return ["" for _ in spans], "empty_pending_manual_annotation"


def policy_base_record(record: dict, policy_name: str) -> Dict:
    duration = float(record["duration"])
    text = str(record.get("text", ""))
    return {
        "id": str(record["id"]),
        "policy": policy_name,
        "duration_sec": duration,
        "text_len": len(text),
        "chars_per_sec": len(text) / duration if duration > 0 else 0.0,
        "language": record.get("language"),
        "source_language": record.get("source_language"),
        "podcast": record.get("podcast"),
        "speaker": record.get("speaker"),
        "wav": record.get("wav"),
        "text": text,
        "source_manifest_id": record.get("source_manifest_id"),
        "source_wav": record.get("source_wav"),
        "source_start_time": record.get("source_start_time"),
        "source_end_time": record.get("source_end_time"),
    }


def parent_reject_record(record: dict, reason: str, policy_name: str) -> Dict:
    output = policy_base_record(record, policy_name)
    output.update(
        {
            "reject_scope": "parent",
            "reason": reason,
        }
    )
    return output


def child_segment_record(
    parent: dict,
    *,
    child_id: str,
    child_wav: str,
    span: Tuple[float, float],
    child_text: str,
    split_index: int,
    split_count: int,
    sample_rate: int,
    policy_name: str,
    text_split_method: str,
) -> dict:
    start, end = span
    duration = max(0.0, end - start)
    child = dict(parent)
    child["id"] = child_id
    child["wav"] = child_wav
    child["duration"] = duration
    child["sampling_rate"] = sample_rate
    child["num_samples"] = int(round(duration * sample_rate))
    child["text"] = child_text

    parent_source_start = safe_float(parent.get("source_start_time"))
    if parent_source_start is not None:
        child["source_start_time"] = parent_source_start + start
        child["source_end_time"] = parent_source_start + end
        child["source_duration"] = duration

    child.update(
        {
            "vad_policy": policy_name,
            "vad_parent_id": parent.get("id"),
            "vad_parent_wav": parent.get("wav"),
            "vad_start_time": start,
            "vad_end_time": end,
            "vad_split_index": split_index,
            "vad_split_count": split_count,
            "raw_cut_source": "source_wav",
            "raw_cut_source_wav": parent.get("source_wav"),
            "raw_cut_start_time": child.get("source_start_time"),
            "raw_cut_end_time": child.get("source_end_time"),
            "audio_write_pending": True,
            "parent_text": parent.get("text", ""),
            "text_split_method": text_split_method,
            "needs_text_annotation": text_split_method == "empty_pending_manual_annotation",
        }
    )
    return child


def child_reject_record(
    child: dict,
    parent: dict,
    *,
    reason: str,
    policy_name: str,
) -> Dict:
    duration = float(child["duration"])
    text = str(child.get("text", ""))
    return {
        "id": child["id"],
        "parent_id": parent["id"],
        "policy": policy_name,
        "reject_scope": "child",
        "reason": reason,
        "duration_sec": duration,
        "text_len": len(text),
        "chars_per_sec": len(text) / duration if duration > 0 else 0.0,
        "language": child.get("language"),
        "source_language": child.get("source_language"),
        "podcast": child.get("podcast"),
        "speaker": child.get("speaker"),
        "wav": child.get("wav"),
        "parent_wav": parent.get("wav"),
        "text": text,
        "parent_text": parent.get("text", ""),
        "text_split_method": child.get("text_split_method"),
        "source_manifest_id": child.get("source_manifest_id"),
        "source_wav": child.get("source_wav"),
        "source_start_time": child.get("source_start_time"),
        "source_end_time": child.get("source_end_time"),
        "vad_start_time": child.get("vad_start_time"),
        "vad_end_time": child.get("vad_end_time"),
        "vad_split_index": child.get("vad_split_index"),
        "vad_split_count": child.get("vad_split_count"),
    }


def annotation_segment_record(
    child: dict,
    parent: dict,
    *,
    source_manifest: Path,
    source_jsonl_index: int,
    post_vad_action: str,
    reject_reason: Optional[str],
    policy_name: str,
) -> Dict:
    duration = float(child["duration"])
    parent_text = str(parent.get("text", ""))
    return {
        "id": child["id"],
        "parent_id": parent["id"],
        "policy": policy_name,
        "source_manifest": str(source_manifest),
        "source_jsonl_index": source_jsonl_index,
        "source_jsonl_line_number": source_jsonl_index + 1,
        "source_manifest_id": parent.get("source_manifest_id"),
        "language": child.get("language"),
        "source_language": child.get("source_language"),
        "podcast": child.get("podcast"),
        "speaker": child.get("speaker"),
        "wav": child.get("wav"),
        "audio_write_pending": child.get("audio_write_pending", True),
        "parent_wav": parent.get("wav"),
        "source_wav": parent.get("source_wav"),
        "source_start_time": child.get("source_start_time"),
        "source_end_time": child.get("source_end_time"),
        "raw_cut_source": child.get("raw_cut_source"),
        "raw_cut_source_wav": child.get("raw_cut_source_wav"),
        "raw_cut_start_time": child.get("raw_cut_start_time"),
        "raw_cut_end_time": child.get("raw_cut_end_time"),
        "vad_start_time": child.get("vad_start_time"),
        "vad_end_time": child.get("vad_end_time"),
        "duration_sec": duration,
        "sampling_rate": child.get("sampling_rate"),
        "num_samples": child.get("num_samples"),
        "vad_split_index": child.get("vad_split_index"),
        "vad_split_count": child.get("vad_split_count"),
        "post_vad_action": post_vad_action,
        "reject_reason": reject_reason,
        "needs_text_annotation": True,
        "text": "",
        "source_text": parent_text,
        "source_text_len": len(parent_text),
        "annotation_text": "",
    }


def vad_candidate_record(record: dict, policy_name: str) -> Dict:
    output = policy_base_record(record, policy_name)
    output.update(
        {
            "reason": "duration_gt_30s_le_60s_vad_candidate",
            "action": "run_vad",
        }
    )
    return output


def iter_sharded_records(path: Path, num_shards: int, shard_index: int) -> Iterator[Tuple[int, dict]]:
    for index, record in enumerate(iter_jsonl(path)):
        if index % num_shards == shard_index:
            yield index, record


def write_summary(path: Path, summary: dict, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} exists; pass --overwrite")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pct(part: float, total: float) -> float:
    return part / total * 100.0 if total else 0.0


def maybe_print_progress(stats: Counter, args: argparse.Namespace) -> None:
    if args.progress_interval <= 0:
        return
    if stats["records_seen"] % args.progress_interval != 0:
        return
    print(
        "records_seen={records_seen:,} kept={kept_unchanged:,} "
        "vad_candidates={vad_candidates:,} parent_rejects={parent_rejects:,} "
        "child_kept={child_kept:,} child_rejects={child_reject_duration:,}".format(
            records_seen=stats["records_seen"],
            kept_unchanged=stats["kept_unchanged"],
            vad_candidates=stats["vad_candidates"],
            parent_rejects=(
                stats["parent_reject_direct_duration"]
                + stats["parent_reject_vad_error"]
                + stats["parent_reject_no_kept_children"]
            ),
            child_kept=stats["child_kept"],
            child_reject_duration=stats["child_reject_duration"],
        ),
        flush=True,
    )


def main() -> None:
    args = get_args()
    if args.vad_min_duration >= args.direct_reject_duration:
        raise ValueError("--vad-min-duration must be smaller than --direct-reject-duration")
    if args.max_child_duration > args.direct_reject_duration:
        raise ValueError("--max-child-duration should not exceed --direct-reject-duration")
    if args.num_shards <= 0:
        raise ValueError("--num-shards must be positive")
    if not 0 <= args.shard_index < args.num_shards:
        raise ValueError("--shard-index must satisfy 0 <= shard_index < num_shards")
    if not args.segment_manifest.is_file():
        raise FileNotFoundError(args.segment_manifest)

    language = args.language.upper()
    output_dir = args.output_dir or (
        args.audio_root / "manifests" / language / args.policy_name
    )
    paths = output_paths(output_dir, language, args.policy_name)

    stats = Counter()
    duration_sums = Counter()
    examples: Dict[str, List[dict]] = {
        "parent_reject": [],
        "child_reject": [],
        "split_map": [],
        "vad_error": [],
    }
    max_examples = 10
    write_post_vad_outputs = not args.classify_only
    write_annotation_segments = (
        write_post_vad_outputs and not args.no_write_annotation_segments
    )
    silero_state = load_silero_backend(args)

    with ExitStack() as stack:
        parent_reject_f = stack.enter_context(
            JsonlWriter(paths["parent_reject"], args.overwrite)
        )
        child_reject_f = stack.enter_context(
            JsonlWriter(paths["child_reject"], args.overwrite)
            if write_post_vad_outputs
            else nullcontext(_NullWriter())
        )
        all_reject_f = stack.enter_context(
            JsonlWriter(paths["all_reject"], args.overwrite)
        )
        split_map_f = stack.enter_context(
            JsonlWriter(paths["split_map"], args.overwrite)
            if write_post_vad_outputs
            else nullcontext(_NullWriter())
        )
        annotation_f = stack.enter_context(
            JsonlWriter(paths["annotation_segments"], args.overwrite)
            if write_annotation_segments
            else nullcontext(_NullWriter())
        )
        vad_candidates_f = stack.enter_context(
            JsonlWriter(paths["vad_candidates"], args.overwrite)
            if args.write_vad_candidates
            else nullcontext(_NullWriter())
        )
        manifest_preview_f = stack.enter_context(
            JsonlWriter(paths["manifest_preview"], args.overwrite)
            if args.write_manifest_preview
            else nullcontext(_NullWriter())
        )
        for original_index, record in iter_sharded_records(
            args.segment_manifest, args.num_shards, args.shard_index
        ):
            if args.max_records > 0 and stats["records_seen"] >= args.max_records:
                break
            stats["records_seen"] += 1
            stats["last_original_index"] = original_index
            duration = float(record["duration"])
            duration_sums["seen"] += duration

            if duration > args.direct_reject_duration:
                reject = parent_reject_record(
                    record,
                    reason=f"duration_gt_{format_threshold(args.direct_reject_duration)}s",
                    policy_name=args.policy_name,
                )
                parent_reject_f.write(reject)
                all_reject_f.write(reject)
                stats["parent_reject_direct_duration"] += 1
                duration_sums["parent_reject_direct_duration"] += duration
                if len(examples["parent_reject"]) < max_examples:
                    examples["parent_reject"].append(reject)
                maybe_print_progress(stats, args)
                continue

            if duration <= args.vad_min_duration:
                stats["kept_unchanged"] += 1
                duration_sums["kept_unchanged"] += duration
                if args.write_manifest_preview:
                    manifest_preview_f.write(record)
                maybe_print_progress(stats, args)
                continue

            stats["vad_candidates"] += 1
            duration_sums["vad_candidates"] += duration
            if args.write_vad_candidates:
                vad_candidates_f.write(vad_candidate_record(record, args.policy_name))
            if args.classify_only:
                if args.write_manifest_preview:
                    manifest_preview_f.write(record)
                maybe_print_progress(stats, args)
                continue

            audio_path = resolve_audio_path(args.audio_root, str(record["wav"]), language)
            try:
                audio, sample_rate = read_audio(audio_path)
                spans, vad_info = run_vad(audio, sample_rate, args, silero_state)
            except Exception as exc:
                reject = parent_reject_record(
                    record,
                    reason=f"vad_error:{type(exc).__name__}:{exc}",
                    policy_name=args.policy_name,
                )
                parent_reject_f.write(reject)
                all_reject_f.write(reject)
                stats["parent_reject_vad_error"] += 1
                duration_sums["parent_reject_vad_error"] += duration
                if len(examples["vad_error"]) < max_examples:
                    examples["vad_error"].append(reject)
                maybe_print_progress(stats, args)
                continue

            if not spans:
                spans = [(0.0, duration)]
                vad_info["fallback_full_span"] = True

            child_texts, text_split_method = split_text_by_duration(
                str(record.get("text", "")), spans, args.text_split_mode
            )
            split_count = len(spans)
            kept_children = []
            rejected_children = []
            for local_index, span in enumerate(spans, start=1):
                child_id = f"{record['id']}_V{local_index:04d}"
                child_wav = planned_child_wav(str(record["wav"]), child_id)
                child = child_segment_record(
                    record,
                    child_id=child_id,
                    child_wav=child_wav,
                    span=span,
                    child_text=child_texts[local_index - 1],
                    split_index=local_index,
                    split_count=split_count,
                    sample_rate=sample_rate,
                    policy_name=args.policy_name,
                    text_split_method=text_split_method,
                )
                child_duration = float(child["duration"])
                if child_duration > args.max_child_duration:
                    reject_reason = (
                        f"post_vad_child_duration_gt_{format_threshold(args.max_child_duration)}s"
                    )
                    reject_child = child_reject_record(
                        child,
                        record,
                        reason=reject_reason,
                        policy_name=args.policy_name,
                    )
                    child_reject_f.write(reject_child)
                    all_reject_f.write(reject_child)
                    annotation_f.write(
                        annotation_segment_record(
                            child,
                            record,
                            source_manifest=args.segment_manifest,
                            source_jsonl_index=original_index,
                            post_vad_action="reject",
                            reject_reason=reject_reason,
                            policy_name=args.policy_name,
                        )
                    )
                    rejected_children.append(reject_child)
                    stats["child_reject_duration"] += 1
                    duration_sums["child_reject_duration"] += child_duration
                    if len(examples["child_reject"]) < max_examples:
                        examples["child_reject"].append(reject_child)
                else:
                    annotation_f.write(
                        annotation_segment_record(
                            child,
                            record,
                            source_manifest=args.segment_manifest,
                            source_jsonl_index=original_index,
                            post_vad_action="keep",
                            reject_reason=None,
                            policy_name=args.policy_name,
                        )
                    )
                    kept_children.append(child)
                    stats["child_kept"] += 1
                    duration_sums["child_kept"] += child_duration

            if kept_children:
                split_record = {
                    "parent_id": record["id"],
                    "policy": args.policy_name,
                    "parent_duration_sec": duration,
                    "parent_wav": record.get("wav"),
                    "vad_backend": args.vad_backend,
                    "vad_info": vad_info,
                    "children": [{"segment": child} for child in kept_children],
                    "rejected_children": rejected_children,
                }
                split_map_f.write(split_record)
                stats["split_parents_with_kept_children"] += 1
                if args.write_manifest_preview:
                    for child in kept_children:
                        manifest_preview_f.write(child)
                if len(examples["split_map"]) < max_examples:
                    examples["split_map"].append(split_record)
            else:
                reject = parent_reject_record(
                    record,
                    reason="vad_no_kept_children",
                    policy_name=args.policy_name,
                )
                reject["child_reject_count"] = len(rejected_children)
                parent_reject_f.write(reject)
                all_reject_f.write(reject)
                stats["parent_reject_no_kept_children"] += 1
                duration_sums["parent_reject_no_kept_children"] += duration
                if len(examples["parent_reject"]) < max_examples:
                    examples["parent_reject"].append(reject)

            maybe_print_progress(stats, args)

    summary = {
        "language": language,
        "policy_name": args.policy_name,
        "segment_manifest": str(args.segment_manifest),
        "audio_root": str(args.audio_root),
        "output_dir": str(output_dir),
        "classify_only": args.classify_only,
        "thresholds_sec": {
            "vad_min_duration": args.vad_min_duration,
            "direct_reject_duration": args.direct_reject_duration,
            "max_child_duration": args.max_child_duration,
        },
        "text_split_mode": args.text_split_mode,
        "text_split_note": (
            "VAD has no word/character timestamps. Default child text is empty; "
            "parent_text is retained and needs_text_annotation marks children "
            "that require manual or later forced-alignment annotation."
        ),
        "num_shards": args.num_shards,
        "shard_index": args.shard_index,
        "stats": {key: int(value) for key, value in sorted(stats.items())},
        "duration_hours": {
            key: float(value) / 3600.0 for key, value in sorted(duration_sums.items())
        },
        "outputs": {
            key: str(value)
            for key, value in paths.items()
            if key
            not in {
                "vad_candidates",
                "manifest_preview",
                "annotation_segments",
                "child_reject",
                "split_map",
            }
            or (key == "vad_candidates" and args.write_vad_candidates)
            or (key == "manifest_preview" and args.write_manifest_preview)
            or (key == "annotation_segments" and write_annotation_segments)
            or (key in {"child_reject", "split_map"} and write_post_vad_outputs)
        },
        "examples": examples,
    }
    write_summary(paths["summary"], summary, args.overwrite)

    print(json.dumps(summary["outputs"], ensure_ascii=False, indent=2))
    print(json.dumps(summary["stats"], ensure_ascii=False, indent=2))


class _NullWriter:
    def write(self, record: dict) -> None:
        return None


if __name__ == "__main__":
    main()
