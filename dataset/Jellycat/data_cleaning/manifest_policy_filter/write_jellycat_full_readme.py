#!/usr/bin/env python3

import argparse
import glob
import json
from pathlib import Path


def get_args():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--summary",
        type=Path,
        help="prepare_jellycat_zh.py 生成的单个 summary JSON。",
    )
    parser.add_argument(
        "--summary-glob",
        help="prepare_jellycat_zh.py 生成的分 shard summary JSON glob。",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="输出 Markdown README 路径。",
    )
    parser.add_argument(
        "--reject-summary",
        type=Path,
        default=None,
        help="可选 hard reject 分布审查 summary JSON。",
    )
    parser.add_argument(
        "--include-vad-policy",
        action="store_true",
        help="显式写入尚未 promote 的 VAD 二次清理策略说明。",
    )
    return parser.parse_args()


def format_duration(seconds: float) -> str:
    hours = seconds / 3600.0
    return f"{hours:,.2f} 小时（{seconds:,.2f} 秒）"


def add_stats(left: dict, right: dict) -> dict:
    output = dict(left)
    for key, value in right.items():
        if isinstance(value, (int, float)):
            output[key] = output.get(key, 0) + value
        elif key not in output:
            output[key] = value
    return output


def load_summaries(args) -> list:
    paths = []
    if args.summary is not None:
        paths.append(args.summary)
    if args.summary_glob:
        paths.extend(Path(path) for path in sorted(glob.glob(args.summary_glob)))
    if not paths:
        raise ValueError("需要提供 --summary 或 --summary-glob")

    summaries = []
    for path in paths:
        with path.open("r", encoding="utf-8") as f:
            summaries.append(json.load(f))
    return summaries


def combine_summaries(summaries: list) -> dict:
    if len(summaries) == 1:
        summary = dict(summaries[0])
        summary["summary_count"] = 1
        return summary

    base = dict(summaries[0])
    total_stats = {}
    per_language_stats = {}
    manifest_paths = {
        "segment_manifest": [],
        "rejected_manifest": [],
        "lhotse_recordings": [],
        "lhotse_supervisions": [],
    }
    for summary in summaries:
        total_stats = add_stats(total_stats, summary.get("total_stats", {}))
        for language, stats in summary.get("per_language_stats", {}).items():
            per_language_stats[language] = add_stats(
                per_language_stats.get(language, {}), stats
            )
        for key in manifest_paths:
            value = summary.get(key)
            if value:
                manifest_paths[key].append(value)

    base["summary_count"] = len(summaries)
    base["total_stats"] = total_stats
    base["per_language_stats"] = per_language_stats
    base["segment_manifest"] = manifest_paths["segment_manifest"]
    base["rejected_manifest"] = manifest_paths["rejected_manifest"]
    base["lhotse_recordings"] = manifest_paths["lhotse_recordings"]
    base["lhotse_supervisions"] = manifest_paths["lhotse_supervisions"]
    base["num_shards"] = len(summaries)
    return base


def as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def render_path_block(title: str, paths) -> list:
    lines = [f"### {title}", ""]
    for path in as_list(paths):
        lines.append(f"- `{path}`")
    lines.append("")
    return lines


def render_optional_path_block(title: str, paths) -> list:
    items = as_list(paths)
    if not items:
        return []
    return render_path_block(title, items)


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def format_number(value, digits: int = 2) -> str:
    if isinstance(value, int):
        return f"{value:,}"
    return f"{float(value):,.{digits}f}"


def main() -> None:
    args = get_args()
    summary = combine_summaries(load_summaries(args))
    reject_summary = load_json(args.reject_summary) if args.reject_summary else None

    total_stats = summary.get("total_stats", {})
    per_language_stats = summary.get("per_language_stats", {})
    id_map_counts = summary.get("id_map_counts", {})
    summary_count = int(summary.get("summary_count", 1))
    num_shards = int(summary.get("num_shards", summary_count))
    original_num_shards = summary.get("original_num_shards")
    is_merged = num_shards == 1 and original_num_shards is not None

    rejected_non_speech = int(total_stats.get("rejected_non_speech_tag", 0))
    rejected_invalid_time = int(total_stats.get("rejected_invalid_time", 0))
    rejected_cut_error = int(total_stats.get("rejected_cut_error", 0))
    podcast_manifest_summary = summary.get("podcast_manifests")

    target_language = summary.get("target_language", "ZH")
    directory_layout = summary.get(
        "directory_layout",
        f"{target_language}/{target_language}_P000000/{target_language}_P000000_S00000/flac/{target_language}_P000000_S00000_W00000000.flac",
    )
    lines = [
        f"# Jellycat {target_language} 全量数据集说明",
        "",
        "## 数据概况",
        "",
        f"- 目标语言：`{summary.get('target_language', 'ZH')}`",
        f"- 原始数据根目录：`{summary.get('raw_root')}`",
        f"- 输出根目录：`{summary.get('output_root')}`",
        f"- Summary 文件数：`{summary_count}`",
        f"- Manifest 组织方式：`{'单文件合并版' if is_merged else f'{num_shards} 个 shard'}`",
    ]
    if args.include_vad_policy:
        lines.extend(
            [
                "",
                "## 长音频筛查与 VAD 切分规则",
                "",
                "- `duration <= 30s`：保留原 utterance 和原 FLAC 路径。",
                "- `30s < duration <= 60s`：对已经切好的 utterance FLAC 做 VAD，按自然语音段切分。",
                "- `duration > 60s`：直接写入二次清理 reject 清单，不再进入 VAD。",
                "- VAD child 如果仍然 `duration > 30s`，该 child 写入二次清理 reject 清单。",
                "- VAD child 的 id 和文件名保留原始 `W` stem，并追加 `_V0001`、`_V0002` 等后缀。",
                "- 二次清理产物先写入版本化 manifest/audio 输出；验证通过后再决定是否 promote 到正式入口。",
                "- 该流程只处理 Jellycat 已切分后的 manifests 和音频目录，不修改 `raw_data`。",
                "",
            ]
        )

    readme_command = (
        f"python dataset/Jellycat/data_cleaning/manifest_policy_filter/write_jellycat_full_readme.py "
        f"--summary /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/{target_language}/jellycat_{target_language}_segments.summary.json "
    )
    if args.reject_summary:
        readme_command += (
            f"--reject-summary /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/{target_language}/jellycat_{target_language}_reject_candidates.summary.json "
        )
    readme_command += (
        f"--output dataset/Jellycat/data_cleaning/raw_to_utterance/reports/Jellycat_{target_language}_full_dataset_readme.md"
    )

    if is_merged:
        lines.append(f"- 原始 shard 数：`{int(original_num_shards)}`")
        lines.append(f"- 合并行数校验：`{summary.get('merged_line_counts')}`")

    lines.extend([
        "",
        "## 音频目录结构",
        "",
        "```text",
        directory_layout,
        "```",
        "",
        "- `P`：podcast 数字编号。",
        "- `S`：该 podcast 下按 episode-local speaker 映射后的数字编号。",
        "- `W`：utterance 数字编号。",
        "- 原始哈希、原始 speaker、原始音频路径等信息保留在 segment manifest 元数据中。",
        "",
        "## 统计摘要",
        "",
        f"- 接收 utterance 数：`{int(total_stats.get('accepted', 0)):,}`",
        f"- 实际新切出的 FLAC 数：`{int(total_stats.get('audio_written', 0)):,}`",
        f"- 复用已存在 FLAC 数：`{int(total_stats.get('audio_reused', 0)):,}`",
        f"- 接收总时长：{format_duration(float(total_stats.get('accepted_duration_sec', 0.0)))}",
        f"- 数字化 podcast 数：`{int(id_map_counts.get('podcasts', 0)):,}`",
        f"- 数字化 speaker key 数：`{int(id_map_counts.get('speakers', 0)):,}`",
        "",
        "## Rejected 统计",
        "",
        f"- 纯标签非语音（`non_speech_tag`）：`{rejected_non_speech:,}`",
        f"- 非法时间标注（`invalid_time`）：`{rejected_invalid_time:,}`",
        f"- 切片失败（`cut_error`）：`{rejected_cut_error:,}`",
        "",
        "## 分语言统计",
        "",
        "| 源语言 | 接收条数 | 接收时长 | 非语音 rejected | 非法时间 rejected | 切片失败 rejected |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for language, stats in sorted(per_language_stats.items()):
        lines.append(
            "| {lang} | {accepted:,} | {duration} | {non_speech:,} | {invalid_time:,} | {cut_error:,} |".format(
                lang=language,
                accepted=int(stats.get("accepted", 0)),
                duration=format_duration(float(stats.get("accepted_duration_sec", 0.0))),
                non_speech=int(stats.get("rejected_non_speech_tag", 0)),
                invalid_time=int(stats.get("rejected_invalid_time", 0)),
                cut_error=int(stats.get("rejected_cut_error", 0)),
            )
        )

    lines.extend(
        [
            "",
            "## Manifest 产物",
            "",
            "以下是当前正式 manifest 入口。",
            "",
        ]
    )
    lines.extend(render_path_block("Segment manifests", summary.get("segment_manifest")))
    lines.extend(render_path_block("Rejected manifests", summary.get("rejected_manifest")))
    lines.extend(render_path_block("Lhotse recordings", summary.get("lhotse_recordings")))
    lines.extend(render_path_block("Lhotse supervisions", summary.get("lhotse_supervisions")))
    if podcast_manifest_summary:
        lines.extend(
            [
                "### Podcast 级 manifests",
                "",
                f"- 根目录：`{podcast_manifest_summary.get('manifest_root')}`",
                f"- 文件模式：`{podcast_manifest_summary.get('manifest_pattern')}`",
                f"- podcast manifest 数：`{int(podcast_manifest_summary.get('num_podcast_manifests', 0)):,}`",
                f"- 总记录数：`{int(podcast_manifest_summary.get('total_records', 0)):,}`",
                f"- 每个 `{target_language}_Pxxxxx.jsonl` 与同名 podcast 音频目录并列，`wav` 字段相对语言根目录，结构仿照 Emilia 的 batch 级 jsonl。",
                "",
            ]
        )
        lines.extend(
            render_optional_path_block(
                "Podcast-level manifest summary",
                podcast_manifest_summary.get("summary_output"),
            )
        )

    if reject_summary:
        distribution = reject_summary.get("distribution", {})
        lines.extend(
            [
                "### Hard reject cleanup manifests",
                "",
                f"- 宽规则候选（`duration > {format_number(reject_summary.get('duration_threshold_sec', 60.0), 0)}s`）：",
                f"  `{reject_summary.get('broad_reject_jsonl')}`",
                f"- 当前选用 hard reject（`duration > {format_number(reject_summary.get('duration_threshold_sec', 60.0), 0)}s and chars_per_sec < {reject_summary.get('chars_per_sec_threshold', 1.0)}`）：",
                f"  `{reject_summary.get('strict_reject_jsonl')}`",
                "- Summary：",
                f"  `{args.reject_summary}`",
                "",
                f"- 宽规则候选数：`{int(reject_summary.get('broad_count', 0)):,}`",
                f"- hard reject 数：`{int(reject_summary.get('strict_count', 0)):,}`",
                f"- 扫描记录数：`{int(distribution.get('records', 0)):,}`",
                f"- 平均时长：`{format_number(distribution.get('duration_mean_sec', 0.0))}` 秒；最大时长：`{format_number(distribution.get('duration_max_sec', 0.0))}` 秒。",
                f"- 平均字符数：`{format_number(distribution.get('text_len_mean', 0.0))}`；平均 chars/sec：`{format_number(distribution.get('chars_per_sec_mean', 0.0))}`。",
                "",
                "当前 hard reject 清单用于后续训练或清理步骤完成后再按 id 删除，避免中途改动已经开始处理的输入。",
                "",
                "生成命令：",
                "",
                "```bash",
                f"python dataset/Jellycat/data_cleaning/manifest_policy_filter/generate_jellycat_reject_list.py --language {target_language} --podcast-root /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/{target_language} --output-dir /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/{target_language} --duration-threshold 60 --chars-per-sec-threshold 1.0",
                "```",
                "",
                "删除命令示例，reject 文件通过参数传入：",
                "",
                "```bash",
                "python dataset/Jellycat/data_cleaning/manifest_policy_filter/filter_jsonl_by_reject_list.py \\",
                f"  --reject-jsonl {reject_summary.get('strict_reject_jsonl')} \\",
                "  --input /path/to/input.jsonl.gz \\",
                "  --output /path/to/output.filtered.jsonl.gz",
                "```",
                "",
            ]
        )

    if is_merged:
        lines.extend(
            [
                "## Shard 备份说明",
                "",
                "- 原始分片 manifest 已合并为单文件 manifest。",
                "- 原始 shard manifest 和 shard summary 已移动到同一 manifest 目录下的备份文件夹，避免下游误用重复入口。",
                "- 当前训练和数据处理应优先使用上方单文件 manifest。",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "## Shard 使用建议",
                "",
                "- 当前 shard 产物已经是完整正式产物，可以直接作为训练和数据处理入口使用。",
                "- 如果下游工具强制要求单个 `.jsonl.gz` 文件，可以使用合并脚本生成单文件兼容版本。",
                "",
            ]
        )

    lines.extend(
        [
            "## 时长策略",
            "",
            "manifest 和 Lhotse 中的时长统一来自目标 FLAC 头信息，即 `num_samples / sampling_rate`。",
            "这与 Emilia 24k stage4 的 recording 时长修正策略保持一致。",
            "",
            "## 复现命令",
            "",
            "```bash",
            f"bash dataset/Jellycat/data_cleaning/raw_to_utterance/run_prepare_jellycat_{target_language.lower()}_shards.sh",
            "python dataset/Jellycat/data_cleaning/raw_to_utterance/merge_jellycat_sharded_manifests.py",
            f"python dataset/Jellycat/data_cleaning/raw_to_utterance/write_jellycat_podcast_manifests.py --segment-manifest /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/{target_language}/jellycat_{target_language}_segments.jsonl.gz --output-root /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat --language {target_language} --summary /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/{target_language}/jellycat_{target_language}_segments.summary.json --summary-output /inspire/qb-ilm/project/embodied-multimodality/chenxie-25019/zhikang/Jellycat/manifests/{target_language}/jellycat_{target_language}_segments.podcast_manifests.summary.json",
            readme_command,
            "```",
        ]
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
