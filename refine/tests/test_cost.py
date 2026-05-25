"""Tests for refine.cost — base cost arithmetic + retry inflation."""

import pytest

from llm.models import MODELS
from refine.cost import (
    COSTS,
    RETRY_COST_INFLATION,
    UnknownModelError,
    base_cost_usd,
    iteration_cost_usd,
)


@pytest.mark.parametrize(
    "key, provider_model_id",
    [(k, c.provider_model_id) for k, c in MODELS.items()],
)
def test_every_registered_model_has_cost_entry(
    key: str, provider_model_id: str
) -> None:
    """Every model in llm.models.MODELS must have a corresponding COSTS
    entry — otherwise the refine loop crashes at iter 1 with
    UnknownModelError. The original miss (gemini-3.5-flash registered
    in v1.1.0 but not priced) is exactly the gap this test plugs."""
    assert provider_model_id in COSTS, (
        f"registry key {key!r} points at provider_model_id "
        f"{provider_model_id!r} which has no cost entry in COSTS"
    )


class TestBaseCostUsd:
    def test_one_million_input_tokens_on_sonnet_costs_three_dollars(self) -> None:
        assert base_cost_usd(
            "claude-sonnet-4-6",
            input_tokens=1_000_000,
            output_tokens=0,
        ) == pytest.approx(3.0)

    def test_one_million_output_tokens_on_sonnet_costs_fifteen_dollars(self) -> None:
        assert base_cost_usd(
            "claude-sonnet-4-6",
            input_tokens=0,
            output_tokens=1_000_000,
        ) == pytest.approx(15.0)

    def test_cache_creation_is_more_expensive_than_input(self) -> None:
        with_cache_create = base_cost_usd(
            "claude-sonnet-4-6",
            input_tokens=0,
            output_tokens=0,
            cache_creation_tokens=1_000_000,
        )
        without = base_cost_usd(
            "claude-sonnet-4-6",
            input_tokens=1_000_000,
            output_tokens=0,
        )
        assert with_cache_create > without

    def test_cache_read_is_one_tenth_of_input(self) -> None:
        cache_read = base_cost_usd(
            "claude-sonnet-4-6",
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=1_000_000,
        )
        plain_input = base_cost_usd(
            "claude-sonnet-4-6",
            input_tokens=1_000_000,
            output_tokens=0,
        )
        assert cache_read == pytest.approx(plain_input * 0.1)

    def test_unknown_model_raises_explicitly(self) -> None:
        with pytest.raises(UnknownModelError, match="claude-grok-9000"):
            base_cost_usd("claude-grok-9000", input_tokens=100, output_tokens=10)

    @pytest.mark.parametrize("model_id", list(COSTS.keys()))
    def test_every_registered_model_can_be_priced(self, model_id: str) -> None:
        """Catches accidental removal of a kind from the cost table."""
        base_cost_usd(model_id, input_tokens=1, output_tokens=1)


class TestIterationCostUsd:
    def test_zero_retries_returns_base_cost(self) -> None:
        assert iteration_cost_usd(1.0, retry_count=0) == 1.0

    def test_one_retry_inflates_by_fifteen_percent(self) -> None:
        assert iteration_cost_usd(1.0, retry_count=1) == pytest.approx(1.15)

    def test_two_retries_inflate_by_thirty_percent(self) -> None:
        """Inflation is linear, not compounding — matches the spec's
        `1 + 0.15 * retries` formula."""
        assert iteration_cost_usd(1.0, retry_count=2) == pytest.approx(1.30)

    def test_negative_retry_count_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            iteration_cost_usd(1.0, retry_count=-1)


def test_inflation_constant_matches_spec() -> None:
    """If this changes, the budget-guard behavior changes; failing here
    forces a deliberate spec update."""
    assert RETRY_COST_INFLATION == 0.15
