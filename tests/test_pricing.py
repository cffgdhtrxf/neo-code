import pytest
from unittest.mock import MagicMock, patch

import neo_code
from neo_code import _get_prices, PRICE_TABLE


class TestGetPrices:
    def test_v4_pro_prices(self):
        prices = _get_prices("deepseek-v4-pro")
        assert prices == (3.0, 0.025, 6.0)

    def test_v4_flash_prices(self):
        prices = _get_prices("deepseek-v4-flash")
        assert prices == (1.0, 0.02, 2.0)

    def test_substring_match(self):
        prices = _get_prices("deepseek-v4-pro-some-variant")
        assert prices == (3.0, 0.025, 6.0)

    def test_unknown_model_falls_back_to_default(self):
        prices = _get_prices("unknown-model-xyz")
        assert prices == PRICE_TABLE["default"]

    def test_all_price_table_keys_are_tuples(self):
        for key, prices in PRICE_TABLE.items():
            assert isinstance(prices, tuple), f"{key} prices should be a tuple"
            assert len(prices) == 3, f"{key} should have 3 prices"
            assert all(isinstance(p, (int, float)) for p in prices)


class TestCostCalculation:
    def test_cost_formula(self, state, mock_client):
        from unittest.mock import MagicMock
        usage = MagicMock()
        usage.total_tokens = 2000
        usage.prompt_tokens = 1500
        usage.completion_tokens = 500
        usage.prompt_cache_hit_tokens = 500

        prompt_tokens = 1500
        cache_hit = 500
        completion_tokens = 500
        cost_input, cost_cached, cost_output = _get_prices("deepseek-v4-pro")
        expected = ((prompt_tokens - cache_hit) / 1_000_000 * cost_input
                    + cache_hit / 1_000_000 * cost_cached
                    + completion_tokens / 1_000_000 * cost_output)
        assert expected > 0

    def test_zero_tokens_cost_zero(self):
        cost_input, cost_cached, cost_output = _get_prices("deepseek-v4-pro")
        cost = (0 / 1_000_000 * cost_input
                + 0 / 1_000_000 * cost_cached
                + 0 / 1_000_000 * cost_output)
        assert cost == 0.0

    def test_cache_hit_reduces_cost(self):
        input_price, cached_price, _ = _get_prices("deepseek-v4-pro")
        cost_no_cache = 1000 / 1_000_000 * input_price
        cost_with_cache = 500 / 1_000_000 * input_price + 500 / 1_000_000 * cached_price
        assert cost_with_cache < cost_no_cache
        assert cached_price < input_price


class TestPrintUsageCostIntegration:
    def test_cost_accumulates_on_state(self, state, mock_client):
        from unittest.mock import MagicMock
        usage = MagicMock()
        usage.total_tokens = 1000
        usage.prompt_tokens = 800
        usage.completion_tokens = 200
        usage.prompt_cache_hit_tokens = 0

        initial_cost = state.session_cost
        neo_code._print_usage(state, mock_client, usage)
        assert state.session_cost > initial_cost

    def test_no_usage_does_nothing(self, state, mock_client):
        initial_cost = state.session_cost
        neo_code._print_usage(state, mock_client, None)
        assert state.session_cost == initial_cost
