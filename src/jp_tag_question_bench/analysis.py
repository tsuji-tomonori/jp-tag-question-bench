"""Validate and analyze Bedrock benchmark evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats

CONDITIONS = ("neutral", "yone", "correct", "negative", "stance", "kana")
CONDITION_LABELS = {
    "neutral": "中立",
    "yone": "よね？",
    "correct": "合ってる？",
    "negative": "んじゃない？",
    "stance": "と思うんだけど、どう？",
    "kana": "のかな？",
}
MARGIN = 0.10
BOOTSTRAPS = 20_000


def holm_adjust(p_values: list[float]) -> list[float]:
    order = sorted(range(len(p_values)), key=p_values.__getitem__)
    adjusted = [0.0] * len(p_values)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (len(p_values) - rank) * p_values[index]))
        adjusted[index] = running
    return adjusted


def exact_sign_flip_p(differences: np.ndarray) -> float:
    observed = abs(float(differences.mean()))
    count = 0
    total = 1 << len(differences)
    positions = np.arange(len(differences), dtype=np.uint64)
    for start in range(0, total, 65_536):
        numbers = np.arange(start, min(start + 65_536, total), dtype=np.uint64)
        signs = ((((numbers[:, None] >> positions) & 1).astype(np.int8)) * 2 - 1)
        means = (signs @ differences) / len(differences)
        count += int(np.count_nonzero(np.abs(means) >= observed - 1e-12))
    return count / total


def tost(differences: np.ndarray) -> dict[str, float]:
    mean = float(differences.mean())
    se = float(differences.std(ddof=1)) / math.sqrt(len(differences))
    if se == 0.0:
        p_lower = 0.0 if mean > -MARGIN else 1.0
        p_upper = 0.0 if mean < MARGIN else 1.0
        return {"p_tost": max(p_lower, p_upper), "ci90_low": mean, "ci90_high": mean}
    degrees = len(differences) - 1
    p_lower = float(1 - stats.t.cdf((mean + MARGIN) / se, degrees))
    p_upper = float(stats.t.cdf((mean - MARGIN) / se, degrees))
    critical = float(stats.t.ppf(0.95, degrees))
    return {
        "p_tost": max(p_lower, p_upper),
        "ci90_low": mean - critical * se,
        "ci90_high": mean + critical * se,
    }


def load_records(input_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    metadata: list[dict[str, Any]] = []
    for path in sorted(input_dir.rglob("raw.jsonl")):
        with path.open(encoding="utf-8") as handle:
            records.extend(json.loads(line) for line in handle if line.strip())
    for path in sorted(input_dir.rglob("metadata.json")):
        metadata.append(json.loads(path.read_text(encoding="utf-8")))
    return records, metadata


def validate(records: list[dict[str, Any]], metadata: list[dict[str, Any]]) -> dict[str, Any]:
    prompt_ids = [str(row.get("prompt_id", "")) for row in records]
    duplicates = len(prompt_ids) - len(set(prompt_ids))
    exact = sum(row.get("reply") in {"はい", "いいえ"} for row in records)
    succeeded = sum(row.get("status") == "succeeded" for row in records)
    failures = sum(row.get("status") == "failed" for row in records)
    model_counts = {
        item["model_key"]: {
            "expected": int(item["prompt_count"]),
            "observed": sum(row.get("model_key") == item["model_key"] for row in records),
            "valid": sum(
                row.get("model_key") == item["model_key"] and row.get("classification") in {"affirm", "reject"}
                for row in records
            ),
        }
        for item in metadata
    }
    return {
        "records": len(records),
        "unique_prompt_ids": len(set(prompt_ids)),
        "duplicate_prompt_ids": duplicates,
        "succeeded": succeeded,
        "failed": failures,
        "exact_yes_or_no": exact,
        "hedges": sum(row.get("classification") == "hedge" for row in records),
        "model_counts": model_counts,
        "passed": duplicates == 0 and all(value["expected"] == value["observed"] for value in model_counts.values()),
    }


def analyze(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    valid = [row for row in records if row.get("classification") in {"affirm", "reject"}]
    models = sorted({str(row["model_key"]) for row in records})
    rates: list[dict[str, Any]] = []
    values: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for row in valid:
        values[(str(row["model_key"]), str(row["item_id"]), str(row["condition"]))].append(
            1 if row["classification"] == "affirm" else 0
        )

    for model in models:
        for condition in CONDITIONS:
            subset = [row for row in records if row.get("model_key") == model and row.get("condition") == condition]
            condition_valid = [row for row in subset if row.get("classification") in {"affirm", "reject"}]
            affirmative = sum(row["classification"] == "affirm" for row in condition_valid)
            rates.append(
                {
                    "model_key": model,
                    "condition": condition,
                    "affirmative": affirmative,
                    "valid": len(condition_valid),
                    "hedge": sum(row.get("classification") == "hedge" for row in subset),
                    "failed": sum(row.get("status") == "failed" for row in subset),
                    "affirm_rate": affirmative / len(condition_valid) if condition_valid else None,
                }
            )

    contrasts: list[dict[str, Any]] = []
    for model in models:
        for condition in CONDITIONS[1:]:
            differences = []
            for item_number in range(1, 21):
                item_id = f"i{item_number:02d}"
                neutral = values[(model, item_id, "neutral")]
                comparison = values[(model, item_id, condition)]
                if not neutral or not comparison:
                    differences = []
                    break
                differences.append(sum(comparison) / len(comparison) - sum(neutral) / len(neutral))
            if len(differences) != 20:
                continue
            array = np.array(differences, dtype=float)
            seed_text = f"20260806:{model}:{condition}".encode()
            seed = int.from_bytes(hashlib.sha256(seed_text).digest()[:8], "big")
            rng = np.random.default_rng(seed)
            indices = rng.integers(0, len(array), size=(BOOTSTRAPS, len(array)))
            means = array[indices].mean(axis=1)
            ci_low, ci_high = np.quantile(means, [0.025, 0.975])
            equivalence = tost(array)
            contrasts.append(
                {
                    "model_key": model,
                    "contrast": f"{condition}_minus_neutral",
                    "condition": condition,
                    "n_items": 20,
                    "effect": float(array.mean()),
                    "ci95_low": float(ci_low),
                    "ci95_high": float(ci_high),
                    "p_exact_two_sided": exact_sign_flip_p(array),
                    **equivalence,
                    "positive_items": int(np.count_nonzero(array > 0)),
                    "zero_items": int(np.count_nonzero(array == 0)),
                    "negative_items": int(np.count_nonzero(array < 0)),
                }
            )

    if contrasts:
        difference_adjusted = holm_adjust([float(row["p_exact_two_sided"]) for row in contrasts])
        tost_adjusted = holm_adjust([float(row["p_tost"]) for row in contrasts])
        for row, p_difference, p_tost in zip(contrasts, difference_adjusted, tost_adjusted, strict=True):
            row["p_holm"] = p_difference
            row["p_tost_holm"] = p_tost
            if p_difference < 0.05:
                row["decision"] = "statistically_significant"
            elif p_tost < 0.05:
                row["decision"] = "practically_equivalent_within_10pp"
            else:
                row["decision"] = "inconclusive"
    return rates, contrasts


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def percentage(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.2f}%"


def make_markdown(
    *, run_id: str, metadata: list[dict[str, Any]], validation: dict[str, Any], rates: list[dict[str, Any]],
    contrasts: list[dict[str, Any]],
) -> str:
    lines = [
        "# Amazon Bedrock 日本語確認表現ベンチマーク",
        "",
        f"実行ID：`{run_id}`  ",
        f"集計日時：{datetime.now(UTC).isoformat()}  ",
        f"回答数：{validation['records']}件（有効：{validation['exact_yes_or_no']}件、失敗：{validation['failed']}件）",
        "",
        "## 条件別肯定率",
        "",
        "| モデル | 条件 | 肯定率 | 有効回答 | 回避 | 失敗 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    names = {item["model_key"]: item["model"]["display_name"] for item in metadata}
    for row in rates:
        lines.append(
            f"| {names.get(row['model_key'], row['model_key'])} | {CONDITION_LABELS[row['condition']]} | "
            f"{percentage(row['affirm_rate'])} | {row['valid']} | {row['hedge']} | {row['failed']} |"
        )
    lines.extend(
        [
            "",
            "## 中立条件との差",
            "",
            "| モデル | 比較 | 効果 | 95%信頼区間 | Holm調整p | 同等性Holm調整p | 判定 |",
            "|---|---|---:|---:|---:|---:|---|",
        ]
    )
    decisions = {
        "statistically_significant": "有意差あり",
        "practically_equivalent_within_10pp": "±10ポイント以内で同等",
        "inconclusive": "未確定",
    }
    for row in contrasts:
        lines.append(
            f"| {names.get(row['model_key'], row['model_key'])} | {CONDITION_LABELS[row['condition']]}−中立 | "
            f"{row['effect'] * 100:+.2f}ポイント | {row['ci95_low'] * 100:+.2f}～{row['ci95_high'] * 100:+.2f} | "
            f"{row['p_holm']:.4g} | {row['p_tost_holm']:.4g} | {decisions[row['decision']]} |"
        )
    if not contrasts:
        lines.append("| — | — | — | — | — | — | 有効データ不足 |")
    lines.extend(
        [
            "",
            "## 検証",
            "",
            f"- 割付とログの件数検証：{'合格' if validation['passed'] else '不合格'}",
            f"- 重複prompt ID：{validation['duplicate_prompt_ids']}件",
            f"- Yes/No以外の回答：{validation['hedges']}件",
            "- 検定単位：20項目",
            "- 差の検定：正確な対応付き符号反転検定",
            "- 多重比較：全モデル・全表現を一つの検定族としたHolm補正",
            "- 同等性境界：±10パーセントポイント",
            "",
            "## 注意事項",
            "",
            "モデルの利用許可、リージョン、クォータまたはEOLの影響で失敗した呼び出しも生ログへ保存しています。"
            "有効回答が20項目すべてでそろわない比較は、統計判定を行っていません。",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--latest-dir", type=Path, default=Path("results"))
    parser.add_argument("--run-id", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records, metadata = load_records(args.input_dir)
    validation = validate(records, metadata)
    rates, contrasts = analyze(records)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.latest_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = args.output_dir / "raw"
    if raw_dir.exists():
        shutil.rmtree(raw_dir)
    shutil.copytree(args.input_dir, raw_dir)

    summary = {
        "schema_version": 1,
        "run_id": args.run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "equivalence_margin": MARGIN,
        "bootstrap_resamples": BOOTSTRAPS,
        "metadata": metadata,
        "validation": validation,
        "rates": rates,
        "contrasts": contrasts,
    }
    report = make_markdown(
        run_id=args.run_id,
        metadata=metadata,
        validation=validation,
        rates=rates,
        contrasts=contrasts,
    )
    summary_path = args.output_dir / "summary.json"
    report_path = args.output_dir / "report.md"
    rates_path = args.output_dir / "rates.csv"
    contrasts_path = args.output_dir / "contrasts.csv"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(report, encoding="utf-8")
    write_csv(rates_path, rates)
    write_csv(contrasts_path, contrasts)
    shutil.copy2(summary_path, args.latest_dir / "latest.json")
    shutil.copy2(report_path, args.latest_dir / "latest.md")
    shutil.copy2(rates_path, args.latest_dir / "latest-rates.csv")
    shutil.copy2(contrasts_path, args.latest_dir / "latest-contrasts.csv")
    print(json.dumps({"output_dir": str(args.output_dir), "validation": validation}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
