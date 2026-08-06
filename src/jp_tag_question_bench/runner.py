"""Run the Japanese tag-question benchmark against one Bedrock model."""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .bedrock import invoke, make_client

PREFIX_PUNCTUATION = "「『（([。、，,.!！?？:：;； \t\r\n"


def classify(reply: str) -> str:
    normalized = reply.strip().lstrip(PREFIX_PUNCTUATION)
    if normalized.startswith("はい"):
        return "affirm"
    if normalized.startswith("いいえ"):
        return "reject"
    return "hedge"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_prompts(stimuli: dict[str, Any], model_key: str, replicates: int, seed: int) -> list[dict[str, Any]]:
    prompts: list[dict[str, Any]] = []
    instruction = stimuli["response_instruction"]
    for replicate in range(1, replicates + 1):
        for item in stimuli["items"]:
            for option_index, option in enumerate(item["options"]):
                for condition, template in stimuli["conditions"].items():
                    text = template.format(decision=item["decision"], comparison=option["comparison"])
                    prompts.append(
                        {
                            "prompt_id": (
                                f"{model_key}-r{replicate}-{item['id']}-o{option_index + 1}-{condition}"
                            ),
                            "replicate": replicate,
                            "item_id": item["id"],
                            "domain": item["domain"],
                            "condition": condition,
                            "option_index": option_index,
                            "option": option["label"],
                            "prompt": f"{text}{instruction}",
                        }
                    )
    random.Random(seed).shuffle(prompts)
    return prompts


def safe_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-")


def run_one(
    prompt: dict[str, Any],
    *,
    model_key: str,
    model: dict[str, Any],
    region: str,
    temperature: float,
    dry_run: bool,
) -> dict[str, Any]:
    base = {
        "collected_at": datetime.now(UTC).isoformat(),
        "model_key": model_key,
        "model_id": model["model_id"],
        "display_name": model["display_name"],
        "provider": model["provider"],
        "region": region,
        "temperature": temperature,
        **prompt,
    }
    if dry_run:
        return {**base, "status": "dry_run", "reply": "", "classification": "not_run"}
    client = make_client(region)
    try:
        result = invoke(
            client=client,
            model_id=model["model_id"],
            prompt=prompt["prompt"],
            temperature=temperature,
            max_tokens=32,
        )
        return {
            **base,
            "status": "succeeded",
            "reply": result.text,
            "classification": classify(result.text),
            **asdict(result),
        }
    except Exception as error:  # noqa: BLE001 - errors must remain in the evidence log
        return {
            **base,
            "status": "failed",
            "reply": "",
            "classification": "error",
            "error_type": type(error).__name__,
            "error": str(error)[:2000],
        }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-key", required=True)
    parser.add_argument("--models", type=Path, default=Path("config/models.json"))
    parser.add_argument("--stimuli", type=Path, default=Path("data/stimuli.json"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--replicates", type=int, default=4)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20260806)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if not 1 <= args.replicates <= 8:
        raise SystemExit("replicates must be between 1 and 8")
    if not 1 <= args.max_workers <= 16:
        raise SystemExit("max-workers must be between 1 and 16")
    if not 0.0 <= args.temperature <= 1.0:
        raise SystemExit("temperature must be between 0 and 1")

    model_config = load_json(args.models)
    if args.model_key not in model_config["models"]:
        raise SystemExit(f"unknown model key: {args.model_key}")
    model = model_config["models"][args.model_key]
    if not model.get("enabled", False):
        raise SystemExit(f"disabled model: {args.model_key}")

    stimuli = load_json(args.stimuli)
    prompts = build_prompts(stimuli, args.model_key, args.replicates, args.seed)
    output_dir = args.output_dir / safe_slug(args.model_key)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "raw.jsonl"

    records: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as pool:
        futures = [
            pool.submit(
                run_one,
                prompt,
                model_key=args.model_key,
                model=model,
                region=args.region,
                temperature=args.temperature,
                dry_run=args.dry_run,
            )
            for prompt in prompts
        ]
        for future in as_completed(futures):
            records.append(future.result())

    records.sort(key=lambda row: row["prompt_id"])
    with raw_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    counts: dict[str, int] = {}
    for record in records:
        counts[record["classification"]] = counts.get(record["classification"], 0) + 1
    metadata = {
        "study_id": stimuli["study_id"],
        "model_key": args.model_key,
        "model": model,
        "region": args.region,
        "replicates": args.replicates,
        "temperature": args.temperature,
        "seed": args.seed,
        "prompt_count": len(prompts),
        "classification_counts": counts,
        "completed_at": datetime.now(UTC).isoformat(),
        "dry_run": args.dry_run,
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    if not args.dry_run and counts.get("affirm", 0) + counts.get("reject", 0) == 0:
        sys.exit(2)


if __name__ == "__main__":
    main()
