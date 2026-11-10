import pytest

from app.domain.pricing import (
    FALLBACK_PRICE,
    MODEL_PRICES,
    ModelPrice,
    estimate_cost_usd,
    estimate_tokens,
    price_for_model,
)


def test_known_model_price() -> None:
    assert price_for_model("gpt-4.1-mini") == ModelPrice(0.40, 1.60)


def test_dated_snapshot_uses_the_longest_matching_base_model() -> None:
    assert price_for_model("gpt-4.1-mini-2025-04-14") == MODEL_PRICES["gpt-4.1-mini"]
    assert price_for_model("gpt-4.1-2025-04-14") == MODEL_PRICES["gpt-4.1"]


def test_unknown_model_falls_back_to_a_conservative_price() -> None:
    price = price_for_model("some-future-model")

    assert price == FALLBACK_PRICE
    assert all(price.input_per_1m_usd >= known.input_per_1m_usd for known in MODEL_PRICES.values())


def test_override_wins() -> None:
    override = ModelPrice(1.0, 2.0)

    assert price_for_model("gpt-4.1-mini", override) is override


def test_estimate_cost() -> None:
    cost = estimate_cost_usd(1_000_000, 500_000, ModelPrice(0.40, 1.60))

    assert cost == pytest.approx(0.40 + 0.80)


def test_negative_token_counts_cost_nothing() -> None:
    assert estimate_cost_usd(-5, -5, ModelPrice(1, 1)) == 0


@pytest.mark.parametrize(("text", "expected"), [("", 0), ("abc", 1), ("a" * 400, 100)])
def test_estimate_tokens(text: str, expected: int) -> None:
    assert estimate_tokens(text) == expected
