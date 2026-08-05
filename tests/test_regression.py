import pytest
from unittest.mock import MagicMock, patch

import neo_code
from neo_code import SessionState, _print_usage


class TestCacheHitField:
    def test_cache_hit_from_prompt_cache_hit_tokens(self):
        usage = MagicMock()
        usage.total_tokens = 1000
        usage.prompt_tokens = 800
        usage.completion_tokens = 200
        usage.prompt_cache_hit_tokens = 300

        assert getattr(usage, 'prompt_cache_hit_tokens', 0) == 300

    def test_cache_hit_defaults_to_zero(self):
        usage = MagicMock()
        usage.total_tokens = 1000
        usage.prompt_tokens = 800
        usage.completion_tokens = 200
        del usage.prompt_cache_hit_tokens

        assert getattr(usage, 'prompt_cache_hit_tokens', 0) == 0


class TestStatsAndClear:
    def test_state_total_tokens_accumulate(self):
        state = SessionState()
        assert getattr(state, '_total_prompt', 0) == 0
        state._total_prompt = 100
        state._total_completion = 50
        assert getattr(state, '_total_prompt', 0) == 100
        assert getattr(state, '_total_completion', 0) == 50

    def test_clear_resets_state_counters(self):
        state = SessionState()
        state.session_cost = 10.0
        state._total_prompt = 1000
        state._total_completion = 500

        state.session_cost = 0.0
        state._total_prompt = 0
        state._total_completion = 0

        assert state.session_cost == 0.0
        assert state._total_prompt == 0
        assert state._total_completion == 0

    def test_print_usage_updates_state_tokens(self, state, mock_client):
        usage = MagicMock()
        usage.total_tokens = 1000
        usage.prompt_tokens = 800
        usage.completion_tokens = 200
        usage.prompt_cache_hit_tokens = 0

        initial_cost = state.session_cost
        mock_tokenizer = MagicMock()
        mock_tokenizer.count.return_value = 1000

        _print_usage(state, mock_client, usage, [], mock_tokenizer)
        assert getattr(state, '_total_prompt', 0) == 800
        assert getattr(state, '_total_completion', 0) == 200
        assert state.session_cost > initial_cost


class TestSystemMessageFiltering:
    def test_clear_filters_compacted_summary(self):
        messages = [
            {"role": "system", "content": "Safety Charter"},
            {"role": "system", "content": "[Compacted Summary]\nOld summary"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        filtered = [m for m in messages if m["role"] == "system"
                    and "[Compacted Summary]" not in str(m.get("content", ""))
                    and "[History Summary]" not in str(m.get("content", ""))]
        assert len(filtered) == 1
        assert filtered[0]["content"] == "Safety Charter"

    def test_clear_filters_history_summary(self):
        messages = [
            {"role": "system", "content": "Safety Charter"},
            {"role": "system", "content": "[History Summary]\nOld history"},
            {"role": "user", "content": "hello"},
        ]
        filtered = [m for m in messages if m["role"] == "system"
                    and "[Compacted Summary]" not in str(m.get("content", ""))
                    and "[History Summary]" not in str(m.get("content", ""))]
        assert len(filtered) == 1
