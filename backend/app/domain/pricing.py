"""Estimated LLM cost from token usage.

Prices are USD per one million tokens (standard tier, verified 2026-11-09 against
OpenAI's published pricing). They are estimates for the budget guard, not invoices.
Override them with ``LLM_INPUT_COST_PER_1M_USD`` / ``LLM_OUTPUT_COST_PER_1M_USD``.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelPrice:
    input_per_1m_usd: float
    output_per_1m_usd: float


MODEL_PRICES: dict[str, ModelPrice] = {
    "gpt-4.1": ModelPrice(2.00, 8.00),
    "gpt-4.1-mini": ModelPrice(0.40, 1.60),
    "gpt-4.1-nano": ModelPrice(0.10, 0.40),
    "gpt-4o": ModelPrice(2.50, 10.00),
    "gpt-4o-mini": ModelPrice(0.15, 0.60),
}

# Used for models missing from the table so that an unknown model can only make the
# budget guard trip early, never late.
FALLBACK_PRICE = ModelPrice(5.00, 20.00)

# Rough characters-per-token ratio for English text, used only when the provider
# did not report usage (mock mode, interrupted streams).
CHARS_PER_TOKEN = 4


def price_for_model(model: str, override: ModelPrice | None = None) -> ModelPrice:
    if override is not None:
        return override
    if model in MODEL_PRICES:
        return MODEL_PRICES[model]
    # Dated snapshots such as "gpt-4.1-mini-2025-04-14" share the base model's price.
    for name in sorted(MODEL_PRICES, key=len, reverse=True):
        if model.startswith(f"{name}-"):
            return MODEL_PRICES[name]
    return FALLBACK_PRICE


def estimate_cost_usd(input_tokens: int, output_tokens: int, price: ModelPrice) -> float:
    cost = (max(input_tokens, 0) * price.input_per_1m_usd + max(output_tokens, 0) * price.output_per_1m_usd) / 1_000_000
    return round(cost, 8)


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // CHARS_PER_TOKEN)
