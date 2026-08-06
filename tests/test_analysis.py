import numpy as np

from jp_tag_question_bench.analysis import analyze, exact_sign_flip_p, holm_adjust


def test_holm_adjust_is_monotone_in_sorted_order() -> None:
    adjusted = holm_adjust([0.01, 0.04, 0.03])
    assert adjusted == [0.03, 0.06, 0.06]


def test_exact_sign_flip_for_zero_effect() -> None:
    assert exact_sign_flip_p(np.zeros(20)) == 1.0


def test_analyze_finds_equivalence_for_identical_conditions() -> None:
    records = []
    for item_number in range(1, 21):
        item_id = f"i{item_number:02d}"
        for condition in ("neutral", "yone"):
            records.append(
                {
                    "model_key": "model-a",
                    "item_id": item_id,
                    "condition": condition,
                    "classification": "affirm" if item_number % 2 else "reject",
                    "status": "succeeded",
                }
            )
    _, contrasts = analyze(records)
    assert len(contrasts) == 1
    assert contrasts[0]["effect"] == 0.0
    assert contrasts[0]["decision"] == "practically_equivalent_within_10pp"


def test_analyze_uses_dynamic_items_and_conditions_from_metadata() -> None:
    records = []
    for item_number in range(1, 4):
        for condition in ("neutral", "custom"):
            records.append(
                {
                    "model_key": "model-a",
                    "item_id": f"q{item_number}",
                    "condition": condition,
                    "classification": "affirm",
                    "status": "succeeded",
                }
            )
    metadata = [
        {
            "model_key": "model-a",
            "stimuli": {
                "conditions": [
                    {"key": "neutral", "label": "中立"},
                    {"key": "custom", "label": "独自表現"},
                ],
                "item_ids": ["q1", "q2", "q3"],
            },
        }
    ]
    rates, contrasts = analyze(records, metadata)
    assert [row["condition"] for row in rates] == ["neutral", "custom"]
    assert contrasts[0]["n_items"] == 3
    assert contrasts[0]["p_method"] == "exact_sign_flip"
