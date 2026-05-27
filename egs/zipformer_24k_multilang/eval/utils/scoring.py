#!/usr/bin/env python3

from __future__ import annotations

import json
import re
import string
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from bench_registry import ICEFALL_ROOT
from icefall.utils import store_transcripts, write_error_stats
from recipe_loader import load_local_module, load_recipe_modules


@dataclass(frozen=True)
class ScoreRecord:
    cut_id: str
    dataset_id: str
    ref_raw_text: str
    ref_normalized_text: str
    hyp_text: str


def _load_zh_metric_functions():
    return load_local_module("zh", "hybrid_text"), load_local_module(
        "zh", "text_normalization"
    )


ZH_HYBRID_TEXT, ZH_TEXT_NORMALIZATION = _load_zh_metric_functions()

EN_APOSTROPHE_TRANSLATION = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "´": "'",
        "`": "'",
    }
)
EN_NORMALIZED_PUNCT_TRANSLATION = str.maketrans(
    {ch: " " for ch in string.punctuation if ch != "'"}
    | {
        "“": " ",
        "”": " ",
        "«": " ",
        "»": " ",
        "‹": " ",
        "›": " ",
        "…": " ",
        "—": " ",
        "–": " ",
        "·": " ",
    }
)
WHITESPACE_PATTERN = re.compile(r"\s+")
ZH_TRADITIONAL_TO_SIMPLIFIED_PAIRS = (
    ("個", "个"),
    ("們", "们"),
    ("來", "来"),
    ("兩", "两"),
    ("這", "这"),
    ("嗎", "吗"),
    ("說", "说"),
    ("質", "质"),
    ("給", "给"),
    ("檔", "档"),
    ("氣", "气"),
    ("資", "资"),
    ("進", "进"),
    ("兒", "儿"),
    ("聯", "联"),
    ("繫", "系"),
    ("係", "系"),
    ("話", "话"),
    ("雲", "云"),
    ("幫", "帮"),
    ("見", "见"),
    ("沒", "没"),
    ("過", "过"),
    ("樣", "样"),
    ("選", "选"),
    ("項", "项"),
    ("農", "农"),
    ("構", "构"),
    ("電", "电"),
    ("腦", "脑"),
    ("試", "试"),
    ("亞", "亚"),
    ("願", "愿"),
    ("報", "报"),
    ("還", "还"),
    ("壞", "坏"),
    ("黨", "党"),
    ("屬", "属"),
    ("實", "实"),
    ("萬", "万"),
    ("輕", "轻"),
    ("邊", "边"),
    ("龍", "龙"),
    ("熱", "热"),
    ("錯", "错"),
    ("羅", "罗"),
    ("問", "问"),
    ("貪", "贪"),
    ("漢", "汉"),
    ("為", "为"),
    ("網", "网"),
    ("遊", "游"),
    ("戲", "戏"),
    ("費", "费"),
    ("獨", "独"),
    ("讀", "读"),
    ("緊", "紧"),
    ("現", "现"),
    ("聽", "听"),
    ("種", "种"),
    ("後", "后"),
    ("動", "动"),
    ("紀", "纪"),
    ("聲", "声"),
    ("鮮", "鲜"),
    ("雞", "鸡"),
    ("曬", "晒"),
    ("覺", "觉"),
    ("細", "细"),
    ("剛", "刚"),
    ("轉", "转"),
    ("開", "开"),
    ("點", "点"),
    ("幾", "几"),
    ("養", "养"),
    ("擺", "摆"),
    ("優", "优"),
    ("勢", "势"),
    ("關", "关"),
    ("單", "单"),
    ("發", "发"),
    ("幹", "干"),
    ("馬", "马"),
    ("識", "识"),
    ("長", "长"),
    ("釋", "释"),
    ("計", "计"),
    ("劃", "划"),
    ("盪", "荡"),
    ("禮", "礼"),
    ("節", "节"),
    ("運", "运"),
    ("區", "区"),
    ("麼", "么"),
    ("強", "强"),
    ("調", "调"),
    ("績", "绩"),
    ("葉", "叶"),
    ("劉", "刘"),
    ("決", "决"),
    ("倫", "伦"),
    ("經", "经"),
    ("將", "将"),
    ("錢", "钱"),
    ("換", "换"),
    ("賽", "赛"),
    ("對", "对"),
    ("處", "处"),
    ("當", "当"),
    ("會", "会"),
    ("臺", "台"),
    ("檯", "台"),
    ("枱", "台"),
    ("灣", "湾"),
    ("體", "体"),
    ("國", "国"),
    ("與", "与"),
    ("專", "专"),
    ("業", "业"),
    ("東", "东"),
    ("絲", "丝"),
    ("丟", "丢"),
    ("嚴", "严"),
    ("喪", "丧"),
    ("豐", "丰"),
    ("臨", "临"),
    ("麗", "丽"),
    ("舉", "举"),
    ("義", "义"),
    ("烏", "乌"),
    ("樂", "乐"),
    ("喬", "乔"),
    ("習", "习"),
    ("鄉", "乡"),
    ("書", "书"),
    ("買", "买"),
    ("亂", "乱"),
    ("爭", "争"),
    ("產", "产"),
    ("畝", "亩"),
    ("親", "亲"),
    ("償", "偿"),
    ("儲", "储"),
    ("兌", "兑"),
    ("蘭", "兰"),
    ("興", "兴"),
    ("獸", "兽"),
    ("內", "内"),
    ("岡", "冈"),
    ("冊", "册"),
    ("寫", "写"),
    ("軍", "军"),
    ("凍", "冻"),
    ("創", "创"),
    ("刪", "删"),
    ("別", "别"),
    ("劇", "剧"),
    ("劍", "剑"),
    ("劑", "剂"),
    ("勁", "劲"),
    ("勞", "劳"),
    ("勛", "勋"),
    ("勳", "勋"),
    ("勵", "励"),
    ("勸", "劝"),
    ("匭", "匦"),
    ("匱", "匮"),
    ("醫", "医"),
    ("華", "华"),
    ("協", "协"),
    ("賣", "卖"),
    ("盧", "卢"),
    ("鹵", "卤"),
    ("衛", "卫"),
    ("卻", "却"),
    ("廠", "厂"),
    ("廳", "厅"),
    ("歷", "历"),
    ("曆", "历"),
    ("厲", "厉"),
    ("壓", "压"),
    ("厭", "厌"),
    ("廁", "厕"),
    ("廚", "厨"),
    ("縣", "县"),
    ("參", "参"),
    ("雙", "双"),
    ("變", "变"),
    ("疊", "叠"),
    ("號", "号"),
    ("嘆", "叹"),
    ("拚", "拼"),
    ("馀", "余"),
    ("劵", "券"),
    ("敎", "教"),
    ("髣", "仿"),
    ("髴", "佛"),
    ("彿", "佛"),
    ("殭", "僵"),
    ("蹤", "踪"),
    ("跡", "迹"),
    ("從", "从"),
    ("掫", "揪"),
    ("鵰", "雕"),
    ("飖", "摇"),
    ("裡", "里"),
    ("裏", "里"),
    ("講", "讲"),
)
ZH_SCRIPT_TRANSLATION = str.maketrans(
    {traditional: simplified for traditional, simplified in ZH_TRADITIONAL_TO_SIMPLIFIED_PAIRS}
)


def _load_speechio_normalizer() -> Optional[Callable[[str], str]]:
    speechio_norm_path = Path(__file__).resolve().parent / "speechio_norm.py"
    if not speechio_norm_path.is_file():
        return None
    import importlib.util

    spec = importlib.util.spec_from_file_location("speechio_norm_hook", speechio_norm_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TextNorm()


SPEECHIO_TEXT_NORM = _load_speechio_normalizer()


def parse_csv(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def write_jsonl(path: Path, rows: Iterable[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _canonical_zh(text: str) -> str:
    text = str(text).translate(ZH_SCRIPT_TRANSLATION)
    return ZH_TEXT_NORMALIZATION.normalize_text(text, "zh")


def _canonical_en(text: str) -> str:
    text_norm = load_local_module("en", "text_normalization")
    return text_norm.normalize_text(text, "en")


def _canonical_eval_en(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text))
    text = text.translate(EN_APOSTROPHE_TRANSLATION)
    text = text.translate(EN_NORMALIZED_PUNCT_TRANSLATION)
    text = WHITESPACE_PATTERN.sub(" ", text).strip()
    return text.upper()


def _char_tokens(text: str) -> List[str]:
    return list("".join(str(text).split()))


def _raw_plain_tokens_zh(text: str) -> List[str]:
    return ZH_HYBRID_TEXT.literal_evaluation_tokens(text)


def _raw_numeric_tokens_zh(text: str) -> List[str]:
    return ZH_HYBRID_TEXT.evaluation_tokens(text)


def _normalized_tokens_zh(text: str) -> List[str]:
    normalized = _canonical_zh(text)
    return ZH_TEXT_NORMALIZATION.reference_tokens(normalized, "zh")


def _normalized_tokens_en(text: str) -> List[str]:
    normalized = _canonical_eval_en(text)
    return normalized.split() if normalized else []


def score_records(
    records: Sequence[ScoreRecord],
    language: str,
    dataset_id: str,
    decode_key: str,
    res_dir: Path,
    suffix: str,
    ref_modes: Sequence[str],
    use_speechio_hook: bool = False,
) -> Dict[str, Optional[float]]:
    results: Dict[str, Optional[float]] = {}

    def build_rows(
        ref_text_selector: Callable[[ScoreRecord], str],
        hyp_transform: Callable[[str], str],
        token_fn: Callable[[str], List[str]],
    ) -> List[Tuple[str, List[str], List[str]]]:
        rows = []
        for record in records:
            ref_text = ref_text_selector(record)
            hyp_text = hyp_transform(record.hyp_text)
            rows.append((record.cut_id, token_fn(ref_text), token_fn(hyp_text)))
        return rows

    metric_builders: Dict[str, Tuple[str, Callable[[], List[Tuple[str, List[str], List[str]]]]]] = {}
    if language.lower() == "zh":
        if "raw" in ref_modes:
            metric_builders["raw-plain"] = (
                "CER",
                lambda: build_rows(
                    lambda record: record.ref_raw_text,
                    lambda text: text,
                    _raw_plain_tokens_zh,
                ),
            )
            metric_builders["raw-numeric-normalized"] = (
                "CER",
                lambda: build_rows(
                    lambda record: record.ref_raw_text,
                    lambda text: text,
                    _raw_numeric_tokens_zh,
                ),
            )
        if "normalized" in ref_modes:
            metric_builders["normalized-plain"] = (
                "CER",
                lambda: build_rows(
                    lambda record: record.ref_normalized_text,
                    _canonical_zh,
                    _normalized_tokens_zh,
                ),
            )
        if "official" in ref_modes and use_speechio_hook and SPEECHIO_TEXT_NORM is not None:
            metric_builders["official-speechio"] = (
                "CER",
                lambda: build_rows(
                    lambda record: SPEECHIO_TEXT_NORM(record.ref_raw_text),
                    lambda text: SPEECHIO_TEXT_NORM(text),
                    _char_tokens,
                ),
            )
    else:
        if "raw" in ref_modes:
            metric_builders["raw-plain"] = (
                "WER",
                lambda: build_rows(
                    lambda record: record.ref_raw_text,
                    lambda text: text,
                    lambda text: text.split(),
                ),
            )
        if "normalized" in ref_modes:
            metric_builders["normalized-plain"] = (
                "WER",
                lambda: build_rows(
                    lambda record: record.ref_normalized_text,
                    _canonical_eval_en,
                    _normalized_tokens_en,
                ),
            )

    res_dir.mkdir(parents=True, exist_ok=True)
    summary_path = res_dir / f"summary-{dataset_id}-{decode_key}-{suffix}.txt"
    summary_lines = ["metric\tunit\tvalue"]

    for metric_name, (unit, builder) in metric_builders.items():
        rows = builder()
        errs_path = res_dir / f"errs-{dataset_id}-{decode_key}-{metric_name}-{suffix}.txt"
        with open(errs_path, "w", encoding="utf-8") as f:
            value = write_error_stats(
                f,
                f"{dataset_id}-{decode_key}-{metric_name}",
                rows,
                enable_log=True,
            )
        results[metric_name] = value
        summary_lines.append(f"{metric_name}\t{unit}\t{value}")

    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("\n".join(summary_lines) + "\n")

    return results


def write_transcripts(
    records: Sequence[ScoreRecord],
    dataset_id: str,
    decode_key: str,
    res_dir: Path,
    suffix: str,
) -> Path:
    recog_path = res_dir / f"recogs-{dataset_id}-{decode_key}-{suffix}.txt"
    store_transcripts(
        filename=recog_path,
        texts=[
            (
                record.cut_id,
                record.ref_raw_text,
                record.hyp_text,
            )
            for record in sorted(records, key=lambda item: item.cut_id)
        ],
    )
    return recog_path
