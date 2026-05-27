#!/usr/bin/env python3

import argparse
import gzip
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont


DEFAULT_MANIFESTS = {
    "ZH": Path(
        "/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/"
        "Jellycat/manifests/ZH/jellycat_ZH_segments.jsonl.gz"
    ),
    "EN": Path(
        "/inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/"
        "Jellycat/manifests/EN/jellycat_EN_segments.jsonl.gz"
    ),
}


DURATION_BINS = [
    0,
    1,
    2,
    3,
    5,
    10,
    15,
    20,
    30,
    45,
    60,
    90,
    120,
    300,
    600,
    math.inf,
]

DURATION_GT30_BINS = [30, 35, 40, 45, 50, 60, 90, 120, 300, 600, math.inf]

CHARS_PER_SEC_BINS = [
    0,
    0.5,
    1.0,
    1.5,
    2.0,
    2.5,
    3.0,
    4.0,
    5.0,
    7.5,
    10.0,
    15.0,
    20.0,
    math.inf,
]


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description=(
            "Compute Jellycat language-level duration and text-density statistics "
            "from segment manifests."
        ),
    )
    parser.add_argument(
        "--manifest",
        action="append",
        default=[],
        metavar="LANG=PATH",
        help=(
            "Language manifest to analyze. Can be repeated. If omitted, the "
            "current official ZH and EN manifests are used."
        ),
    )
    parser.add_argument(
        "--post-policy-manifest",
        action="append",
        default=[],
        metavar="LANG=PATH",
        help=(
            "Optional cleaned/split manifest after the final policy. If provided, "
            "the report compares it with the original manifest for that language."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("analysis"),
        help="Directory for Markdown reports and PNG plots.",
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=-1,
        help="Optional development cap per manifest.",
    )
    parser.add_argument(
        "--progress-interval",
        type=int,
        default=1000000,
        help="Print a progress line every N manifest records; set <=0 to disable.",
    )
    return parser.parse_args()


def parse_lang_paths(items: Iterable[str]) -> Dict[str, Path]:
    paths = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Expected LANG=PATH, got: {item}")
        lang, path = item.split("=", 1)
        lang = lang.strip().upper()
        if not lang:
            raise ValueError(f"Missing language in: {item}")
        paths[lang] = Path(path)
    return paths


def open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def bin_labels(edges: List[float]) -> List[str]:
    labels = []
    for left, right in zip(edges, edges[1:]):
        if math.isinf(right):
            labels.append(f"[{format_edge(left)},+inf)")
        else:
            labels.append(f"[{format_edge(left)},{format_edge(right)})")
    return labels


def format_edge(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return str(value)


def find_bin(value: float, edges: List[float]) -> Optional[int]:
    if value < edges[0]:
        return None
    for index, (left, right) in enumerate(zip(edges, edges[1:])):
        if left <= value < right:
            return index
    return len(edges) - 2


@dataclass
class ThresholdStats:
    count: int = 0
    duration_sec: float = 0.0
    text_len: int = 0

    def add(self, duration: float, text_len: int) -> None:
        self.count += 1
        self.duration_sec += duration
        self.text_len += text_len


@dataclass
class ManifestStats:
    language: str
    path: Path
    count: int = 0
    total_duration_sec: float = 0.0
    total_text_len: int = 0
    total_chars_per_sec: float = 0.0
    min_duration_sec: Optional[float] = None
    max_duration_sec: Optional[float] = None
    min_text_len: Optional[int] = None
    max_text_len: Optional[int] = None
    duration_bins: List[int] = field(
        default_factory=lambda: [0] * (len(DURATION_BINS) - 1)
    )
    duration_bin_seconds: List[float] = field(
        default_factory=lambda: [0.0] * (len(DURATION_BINS) - 1)
    )
    duration_gt30_bins: List[int] = field(
        default_factory=lambda: [0] * (len(DURATION_GT30_BINS) - 1)
    )
    duration_gt30_bin_seconds: List[float] = field(
        default_factory=lambda: [0.0] * (len(DURATION_GT30_BINS) - 1)
    )
    chars_per_sec_bins: List[int] = field(
        default_factory=lambda: [0] * (len(CHARS_PER_SEC_BINS) - 1)
    )
    chars_per_sec_gt30_bins: List[int] = field(
        default_factory=lambda: [0] * (len(CHARS_PER_SEC_BINS) - 1)
    )
    gt30: ThresholdStats = field(default_factory=ThresholdStats)
    gt60: ThresholdStats = field(default_factory=ThresholdStats)
    gt30_le60: ThresholdStats = field(default_factory=ThresholdStats)

    def add(self, duration: float, text_len: int) -> None:
        self.count += 1
        self.total_duration_sec += duration
        self.total_text_len += text_len
        chars_per_sec = text_len / duration if duration > 0 else 0.0
        self.total_chars_per_sec += chars_per_sec
        self.min_duration_sec = (
            duration
            if self.min_duration_sec is None
            else min(self.min_duration_sec, duration)
        )
        self.max_duration_sec = (
            duration
            if self.max_duration_sec is None
            else max(self.max_duration_sec, duration)
        )
        self.min_text_len = text_len if self.min_text_len is None else min(self.min_text_len, text_len)
        self.max_text_len = text_len if self.max_text_len is None else max(self.max_text_len, text_len)

        duration_bin = find_bin(duration, DURATION_BINS)
        if duration_bin is not None:
            self.duration_bins[duration_bin] += 1
            self.duration_bin_seconds[duration_bin] += duration
        if duration > 30:
            self.gt30.add(duration, text_len)
            gt30_bin = find_bin(duration, DURATION_GT30_BINS)
            if gt30_bin is not None:
                self.duration_gt30_bins[gt30_bin] += 1
                self.duration_gt30_bin_seconds[gt30_bin] += duration
            cps_gt30_bin = find_bin(chars_per_sec, CHARS_PER_SEC_BINS)
            if cps_gt30_bin is not None:
                self.chars_per_sec_gt30_bins[cps_gt30_bin] += 1
        if duration > 60:
            self.gt60.add(duration, text_len)
        if 30 < duration <= 60:
            self.gt30_le60.add(duration, text_len)

        cps_bin = find_bin(chars_per_sec, CHARS_PER_SEC_BINS)
        if cps_bin is not None:
            self.chars_per_sec_bins[cps_bin] += 1

    @property
    def mean_duration_sec(self) -> float:
        return self.total_duration_sec / self.count if self.count else 0.0

    @property
    def mean_text_len(self) -> float:
        return self.total_text_len / self.count if self.count else 0.0

    @property
    def mean_chars_per_sec(self) -> float:
        return self.total_chars_per_sec / self.count if self.count else 0.0

    @property
    def global_chars_per_sec(self) -> float:
        return self.total_text_len / self.total_duration_sec if self.total_duration_sec else 0.0


def scan_manifest(
    language: str,
    path: Path,
    max_records: int,
    progress_interval: int,
) -> ManifestStats:
    if not path.is_file():
        raise FileNotFoundError(path)
    stats = ManifestStats(language=language, path=path)
    with open_text(path) as f:
        for index, line in enumerate(f, start=1):
            if max_records > 0 and index > max_records:
                break
            if not line.strip():
                continue
            record = json.loads(line)
            duration = float(record["duration"])
            text = str(record.get("text", ""))
            stats.add(duration=duration, text_len=len(text))
            if progress_interval > 0 and stats.count % progress_interval == 0:
                print(
                    f"  {language}: records={stats.count:,} "
                    f"hours={stats.total_duration_sec / 3600.0:,.2f}",
                    flush=True,
                )
    return stats


def pct(part: float, total: float) -> float:
    return (part / total * 100.0) if total else 0.0


def fmt_int(value: int) -> str:
    return f"{value:,}"


def fmt_float(value: float, digits: int = 4) -> str:
    return f"{value:,.{digits}f}"


def fmt_hours(seconds: float) -> str:
    return f"{seconds / 3600.0:,.2f}"


def distribution_table(labels: List[str], counts: List[int], total: int) -> str:
    rows = ["| Bin | Count | Percent |", "|---|---:|---:|"]
    for label, count in zip(labels, counts):
        rows.append(f"| `{label}` | {fmt_int(count)} | {fmt_float(pct(count, total), 4)} |")
    return "\n".join(rows)


def duration_distribution_table(
    labels: List[str],
    counts: List[int],
    duration_seconds: List[float],
    total_count: int,
    total_duration_seconds: float,
) -> str:
    rows = [
        "| Bin | Count | Count percent | Hours | Duration percent |",
        "|---|---:|---:|---:|---:|",
    ]
    for label, count, seconds in zip(labels, counts, duration_seconds):
        rows.append(
            f"| `{label}` | {fmt_int(count)} | "
            f"{fmt_float(pct(count, total_count), 4)} | "
            f"{fmt_hours(seconds)} | "
            f"{fmt_float(pct(seconds, total_duration_seconds), 4)} |"
        )
    return "\n".join(rows)


def threshold_row(label: str, stats: ManifestStats, dropped: ThresholdStats) -> str:
    kept_count = stats.count - dropped.count
    kept_duration = stats.total_duration_sec - dropped.duration_sec
    return (
        f"| {label} | {fmt_int(dropped.count)} | "
        f"{fmt_float(pct(dropped.count, stats.count), 4)} | "
        f"{fmt_hours(dropped.duration_sec)} | "
        f"{fmt_float(pct(dropped.duration_sec, stats.total_duration_sec), 4)} | "
        f"{fmt_int(kept_count)} | {fmt_hours(kept_duration)} |"
    )


def compare_post_policy_row(
    original: ManifestStats, cleaned: Optional[ManifestStats]
) -> str:
    if cleaned is None:
        return (
            "| Final policy after VAD | pending VAD output | pending | pending | "
            "pending | pending | pending |"
        )
    removed_duration = original.total_duration_sec - cleaned.total_duration_sec
    count_delta = original.count - cleaned.count
    return (
        f"| Final policy after VAD | {fmt_int(count_delta)} | "
        f"{fmt_float(pct(count_delta, original.count), 4)} | "
        f"{fmt_hours(removed_duration)} | "
        f"{fmt_float(pct(removed_duration, original.total_duration_sec), 4)} | "
        f"{fmt_int(cleaned.count)} | {fmt_hours(cleaned.total_duration_sec)} |"
    )


def draw_bar_chart(
    *,
    title: str,
    labels: List[str],
    values: List[float],
    output_path: Path,
    tick_formatter: Callable[[float], str],
    percent_denominator: Optional[float] = None,
    width: int = 1200,
    height: int = 720,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 18)
        small_font = ImageFont.truetype("DejaVuSans.ttf", 13)
    except OSError:
        font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    margin_left = 90
    margin_right = 35
    margin_top = 70
    margin_bottom = 150
    chart_w = width - margin_left - margin_right
    chart_h = height - margin_top - margin_bottom
    max_value = max(values) if values else 0
    max_value = max(max_value, 1.0)
    total_value = percent_denominator if percent_denominator is not None else sum(values)

    draw.text((margin_left, 25), title, fill=(20, 20, 20), font=font)
    draw.line(
        [(margin_left, margin_top), (margin_left, margin_top + chart_h)],
        fill=(60, 60, 60),
        width=2,
    )
    draw.line(
        [
            (margin_left, margin_top + chart_h),
            (margin_left + chart_w, margin_top + chart_h),
        ],
        fill=(60, 60, 60),
        width=2,
    )

    tick_count = 5
    for i in range(tick_count + 1):
        value = max_value * i / tick_count
        y = margin_top + chart_h - int(chart_h * i / tick_count)
        draw.line([(margin_left - 5, y), (margin_left + chart_w, y)], fill=(230, 230, 230))
        draw.text(
            (8, y - 8),
            tick_formatter(value),
            fill=(70, 70, 70),
            font=small_font,
        )

    if not values:
        image.save(output_path)
        return

    bar_gap = 8
    slot_w = chart_w / len(values)
    bar_w = max(4, int(slot_w - bar_gap))
    for i, (label, value) in enumerate(zip(labels, values)):
        x0 = margin_left + int(i * slot_w + bar_gap / 2)
        x1 = x0 + bar_w
        bar_h = int(chart_h * value / max_value)
        y0 = margin_top + chart_h - bar_h
        y1 = margin_top + chart_h
        draw.rectangle([x0, y0, x1, y1], fill=(42, 106, 154))
        percent_label = f"{pct(value, total_value):.2f}%"
        if bar_h > 18:
            draw.text((x0 + 2, y0 + 3), percent_label, fill="white", font=small_font)
        else:
            draw.text((x0 + 2, max(margin_top, y0 - 18)), percent_label, fill=(40, 40, 40), font=small_font)

        label_image = Image.new("RGBA", (160, 22), (255, 255, 255, 0))
        label_draw = ImageDraw.Draw(label_image)
        label_draw.text((0, 0), label, fill=(40, 40, 40), font=small_font)
        rotated = label_image.rotate(55, expand=True)
        image.paste(rotated, (x0 - 8, margin_top + chart_h + 10), rotated)

    image.save(output_path)


def write_language_report(
    *,
    stats_by_language: Dict[str, ManifestStats],
    post_policy_by_language: Dict[str, ManifestStats],
    output_dir: Path,
) -> None:
    lines = [
        "# Jellycat Language Statistics",
        "",
        "Generated from segment-level Jellycat manifests.",
        "",
        "Boundary conventions:",
        "",
        "- `>30s` means `duration > 30.0`.",
        "- `30-60s VAD candidates` means `30.0 < duration <= 60.0`.",
        "- `>60s` means `duration > 60.0`.",
        "- Final policy impact is computed only when a post-policy manifest is supplied.",
        "",
        "## Overview",
        "",
        "| Language | Records | Hours | Mean duration | Min duration | Max duration | Mean text len | Global chars/sec |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for language, stats in stats_by_language.items():
        lines.append(
            f"| {language} | {fmt_int(stats.count)} | {fmt_hours(stats.total_duration_sec)} | "
            f"{fmt_float(stats.mean_duration_sec, 4)} | {fmt_float(stats.min_duration_sec or 0, 4)} | "
            f"{fmt_float(stats.max_duration_sec or 0, 4)} | {fmt_float(stats.mean_text_len, 4)} | "
            f"{fmt_float(stats.global_chars_per_sec, 4)} |"
        )

    lines.extend(["", "## Long Audio Impact", ""])
    for language, stats in stats_by_language.items():
        lines.extend(
            [
                f"### {language}",
                "",
                "| Scenario | Removed record delta | Removed record percent | Removed hours | Removed duration percent | Remaining records | Remaining hours |",
                "|---|---:|---:|---:|---:|---:|---:|",
                threshold_row("Drop all `duration > 30s`", stats, stats.gt30),
                threshold_row("Drop all `duration > 60s`", stats, stats.gt60),
                compare_post_policy_row(stats, post_policy_by_language.get(language)),
                "",
                "| Subset | Records | Percent | Hours | Duration percent | Mean duration | Mean text len | Global chars/sec |",
                "|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for label, subset in (
            ("`duration > 30s`", stats.gt30),
            ("`30s < duration <= 60s` VAD candidates", stats.gt30_le60),
            ("`duration > 60s` direct rejects", stats.gt60),
        ):
            lines.append(
                f"| {label} | {fmt_int(subset.count)} | {fmt_float(pct(subset.count, stats.count), 4)} | "
                f"{fmt_hours(subset.duration_sec)} | {fmt_float(pct(subset.duration_sec, stats.total_duration_sec), 4)} | "
                f"{fmt_float(subset.duration_sec / subset.count if subset.count else 0, 4)} | "
                f"{fmt_float(subset.text_len / subset.count if subset.count else 0, 4)} | "
                f"{fmt_float(subset.text_len / subset.duration_sec if subset.duration_sec else 0, 4)} |"
            )
        lines.append("")

    lines.extend(["## Duration Distributions", ""])
    for language, stats in stats_by_language.items():
        lines.extend(
            [
                f"### {language} Overall",
                "",
                f"![{language} duration distribution]({language}_duration_distribution.png)",
                "",
                duration_distribution_table(
                    bin_labels(DURATION_BINS),
                    stats.duration_bins,
                    stats.duration_bin_seconds,
                    stats.count,
                    stats.total_duration_sec,
                ),
                "",
                f"### {language} Duration > 30s Focus",
                "",
                f"![{language} duration >30s distribution]({language}_duration_gt30_distribution.png)",
                "",
                duration_distribution_table(
                    bin_labels(DURATION_GT30_BINS),
                    stats.duration_gt30_bins,
                    stats.duration_gt30_bin_seconds,
                    stats.gt30.count,
                    stats.gt30.duration_sec,
                ),
                "",
            ]
        )

    lines.extend(["## Characters Per Second Distributions", ""])
    for language, stats in stats_by_language.items():
        lines.extend(
            [
                f"### {language} Overall",
                "",
                f"![{language} chars/sec distribution]({language}_chars_per_sec_distribution.png)",
                "",
                distribution_table(
                    bin_labels(CHARS_PER_SEC_BINS),
                    stats.chars_per_sec_bins,
                    stats.count,
                ),
                "",
                f"### {language} Duration > 30s Focus",
                "",
                f"![{language} chars/sec >30s distribution]({language}_chars_per_sec_gt30_distribution.png)",
                "",
                distribution_table(
                    bin_labels(CHARS_PER_SEC_BINS),
                    stats.chars_per_sec_gt30_bins,
                    stats.gt30.count,
                ),
                "",
            ]
        )

    report_path = output_dir / "jellycat_language_stats.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = get_args()
    manifests = parse_lang_paths(args.manifest) if args.manifest else dict(DEFAULT_MANIFESTS)
    post_policy_paths = parse_lang_paths(args.post_policy_manifest)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    stats_by_language: Dict[str, ManifestStats] = {}
    for language, path in manifests.items():
        print(f"Scanning {language}: {path}", flush=True)
        stats_by_language[language] = scan_manifest(
            language,
            path,
            args.max_records,
            args.progress_interval,
        )

    post_policy_by_language: Dict[str, ManifestStats] = {}
    for language, path in post_policy_paths.items():
        print(f"Scanning post-policy {language}: {path}", flush=True)
        post_policy_by_language[language] = scan_manifest(
            language,
            path,
            args.max_records,
            args.progress_interval,
        )

    for language, stats in stats_by_language.items():
        draw_bar_chart(
            title=f"{language} duration distribution by total hours",
            labels=bin_labels(DURATION_BINS),
            values=[seconds / 3600.0 for seconds in stats.duration_bin_seconds],
            output_path=args.output_dir / f"{language}_duration_distribution.png",
            tick_formatter=lambda value: f"{value:,.0f}h",
            percent_denominator=stats.total_duration_sec / 3600.0,
        )
        draw_bar_chart(
            title=f"{language} duration distribution by total hours, duration > 30s",
            labels=bin_labels(DURATION_GT30_BINS),
            values=[seconds / 3600.0 for seconds in stats.duration_gt30_bin_seconds],
            output_path=args.output_dir / f"{language}_duration_gt30_distribution.png",
            tick_formatter=lambda value: f"{value:,.0f}h",
            percent_denominator=stats.gt30.duration_sec / 3600.0,
        )
        draw_bar_chart(
            title=f"{language} characters per second distribution",
            labels=bin_labels(CHARS_PER_SEC_BINS),
            values=[float(count) for count in stats.chars_per_sec_bins],
            output_path=args.output_dir / f"{language}_chars_per_sec_distribution.png",
            tick_formatter=lambda value: fmt_int(int(value)),
            percent_denominator=float(stats.count),
        )
        draw_bar_chart(
            title=f"{language} characters per second, duration > 30s",
            labels=bin_labels(CHARS_PER_SEC_BINS),
            values=[float(count) for count in stats.chars_per_sec_gt30_bins],
            output_path=args.output_dir / f"{language}_chars_per_sec_gt30_distribution.png",
            tick_formatter=lambda value: fmt_int(int(value)),
            percent_denominator=float(stats.gt30.count),
        )

    write_language_report(
        stats_by_language=stats_by_language,
        post_policy_by_language=post_policy_by_language,
        output_dir=args.output_dir,
    )
    print(f"Wrote report: {args.output_dir / 'jellycat_language_stats.md'}")


if __name__ == "__main__":
    main()
