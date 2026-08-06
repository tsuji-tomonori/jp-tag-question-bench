from pathlib import Path

import pytest

from jp_tag_question_bench.bedrock import extract_text
from jp_tag_question_bench.runner import build_prompts, classify, load_json, validate_stimuli


def test_extract_text_joins_converse_content() -> None:
    response = {"output": {"message": {"content": [{"text": "はい"}, {"text": "。"}]}}}
    assert extract_text(response) == "はい。"


def test_classify_uses_prefix_rule() -> None:
    assert classify("はい") == "affirm"
    assert classify("「いいえ」") == "reject"
    assert classify("判断できません") == "hedge"


def test_build_prompts_is_balanced() -> None:
    stimuli = load_json(Path("data/stimuli.json"))
    validate_stimuli(stimuli)
    prompts = build_prompts(stimuli, "test-model", replicates=2, seed=1)
    assert len(prompts) == 20 * 2 * 6 * 2
    assert len({row["prompt_id"] for row in prompts}) == len(prompts)
    assert {row["condition"] for row in prompts} == set(stimuli["conditions"])
    assert all("\n\n「はい」か「いいえ」だけで答えて。" in row["prompt"] for row in prompts)


def test_custom_stimuli_supports_dynamic_conditions_and_placeholders() -> None:
    stimuli = {
        "study_id": "custom-study",
        "response_instruction": "はいかいいえで答えて。",
        "prompt_separator": "\n--\n",
        "condition_labels": {"neutral": "中立", "confirm": "確認"},
        "conditions": {
            "neutral": "{decision}なら{option}がいい？",
            "confirm": "{domain}の話だけど、{comparison}で合ってる？",
        },
        "items": [
            {
                "id": f"item-{index}",
                "decision": "飲み物",
                "domain": "taste",
                "options": [
                    {"label": "水", "comparison": "水のほう"},
                    {"label": "お茶", "comparison": "お茶のほう"},
                ],
            }
            for index in range(2)
        ],
    }
    validate_stimuli(stimuli)
    prompts = build_prompts(stimuli, "model", replicates=1, seed=1)
    assert len(prompts) == 2 * 2 * 2
    assert all("\n--\nはいかいいえで答えて。" in row["prompt"] for row in prompts)


def test_stimuli_validation_rejects_unknown_placeholder() -> None:
    stimuli = load_json(Path("data/stimuli.json"))
    stimuli["conditions"]["broken"] = "{unknown}でいい？"
    with pytest.raises(SystemExit, match="unknown placeholders"):
        validate_stimuli(stimuli)
