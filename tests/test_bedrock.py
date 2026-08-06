from jp_tag_question_bench.bedrock import extract_text
from jp_tag_question_bench.runner import build_prompts, classify, load_json


def test_extract_text_joins_converse_content() -> None:
    response = {"output": {"message": {"content": [{"text": "はい"}, {"text": "。"}]}}}
    assert extract_text(response) == "はい。"


def test_classify_uses_prefix_rule() -> None:
    assert classify("はい") == "affirm"
    assert classify("「いいえ」") == "reject"
    assert classify("判断できません") == "hedge"


def test_build_prompts_is_balanced() -> None:
    stimuli = load_json(__import__("pathlib").Path("data/stimuli.json"))
    prompts = build_prompts(stimuli, "test-model", replicates=2, seed=1)
    assert len(prompts) == 20 * 2 * 6 * 2
    assert len({row["prompt_id"] for row in prompts}) == len(prompts)
    assert {row["condition"] for row in prompts} == set(stimuli["conditions"])

