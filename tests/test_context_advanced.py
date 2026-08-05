import pytest
from unittest.mock import patch, MagicMock

import neo_code
from neo_code import (
    truncate_context,
    compact_context,
    enhanced_compact,
    _check_single_tool_result_size,
    _find_round_boundary_at_token,
)


def sample_messages(num_rounds=10):
    msgs = [{"role": "system", "content": "System prompt"}]
    for i in range(num_rounds):
        msgs.append({"role": "user", "content": f"question {i}"})
        msgs.append({"role": "assistant", "content": f"answer {i}"})
    return msgs


class TestTruncateContext:
    def test_keeps_system_prompts(self):
        msgs = [
            {"role": "system", "content": "s1"},
            {"role": "system", "content": "s2"},
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
        ]
        result = truncate_context(msgs, keep_rounds=5)
        systems = [m for m in result if m["role"] == "system"]
        assert len(systems) == 2

    def test_keeps_recent_rounds(self):
        msgs = sample_messages(10)
        result = truncate_context(msgs, keep_rounds=3)
        user_msgs = [m["content"] for m in result if m["role"] == "user"]
        assert len(user_msgs) == 3
        assert user_msgs == ["question 7", "question 8", "question 9"]

    def test_fewer_rounds_than_keep_returns_all(self, mock_tokenizer):
        msgs = sample_messages(2)
        result = truncate_context(msgs, keep_rounds=5)
        assert len(result) == len(msgs)

    def test_no_user_messages_returns_all(self):
        msgs = [{"role": "system", "content": "s"}, {"role": "assistant", "content": "a"}]
        result = truncate_context(msgs, keep_rounds=3)
        assert len(result) == 2


class TestCompactContext:
    def test_less_than_keep_rounds_returns_unchanged(self, mock_client, mock_tokenizer):
        msgs = sample_messages(3)
        mock_tokenizer.count.return_value = 100
        mock_client.flash_chat.return_value = None
        with patch.object(neo_code, '_HAS_VECTOR_MEMORY', False):
            result = compact_context(mock_client, msgs, mock_tokenizer, keep_recent=10)
            assert len(result) <= len(msgs) + 3

    def test_compact_reduces_messages(self, mock_client, mock_tokenizer):
        msgs = sample_messages(10)
        mock_client.flash_chat.return_value = "This is a test summary."
        mock_tokenizer.count.return_value = 500
        result = compact_context(mock_client, msgs, mock_tokenizer, keep_recent=2)
        assert len(result) < len(msgs), f"Expected fewer messages, got {len(result)} vs {len(msgs)}"
        has_compacted = any("[Conversation compacted" in str(m.get("content", "")) for m in result)
        assert has_compacted

    def test_compact_with_existing_summary(self, mock_client, mock_tokenizer):
        msgs = [
            {"role": "system", "content": "Safety Charter"},
            {"role": "system", "content": "[Compacted Summary]\nOld summary text"},
            {"role": "user", "content": "new question"},
            {"role": "assistant", "content": "new answer"},
        ]
        mock_client.flash_chat.return_value = "Updated summary."
        mock_tokenizer.count.return_value = 500
        result = compact_context(mock_client, msgs, mock_tokenizer, keep_recent=5)
        content = [m["content"] for m in result if m["role"] == "system" and "[Compacted Summary]" in str(m.get("content", ""))]
        assert len(content) == 1
        assert "Updated summary" in content[0]

    def test_compact_filters_conversation_compacted(self, mock_client, mock_tokenizer):
        msgs = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "assistant", "content": "[Conversation compacted. Ready for next query.]"},
            {"role": "user", "content": "q2"},
            {"role": "assistant", "content": "a2"},
        ]
        mock_client.flash_chat.return_value = "Summary."
        mock_tokenizer.count.return_value = 500
        result = compact_context(mock_client, msgs, mock_tokenizer, keep_recent=1)
        compacted_msgs = [m for m in result if "[Conversation compacted" in str(m.get("content", ""))]
        assert len(compacted_msgs) == 1

    def test_compact_flash_failure_returns_unchanged(self, mock_client, mock_tokenizer):
        msgs = sample_messages(10)
        mock_client.flash_chat.side_effect = Exception("API error")
        mock_tokenizer.count.return_value = 500
        result = compact_context(mock_client, msgs, mock_tokenizer, keep_recent=5)
        assert len(result) == len(msgs)


class TestMicroCompactAdvanced:
    def test_tool_messages_truncated(self):
        long_content = "x" * 5000
        msgs = [
            {"role": "tool", "content": long_content, "tool_call_id": "1"},
            {"role": "user", "content": "short"},
        ]
        result = enhanced_compact(msgs, max_result_len=1000)
        assert len(result[0]["content"]) < len(long_content)

    def test_non_string_tool_content_passed_through(self):
        msgs = [{"role": "tool", "content": None, "tool_call_id": "1"}]
        result = enhanced_compact(msgs)
        assert result[0]["content"] is None


class TestFindRoundBoundary:
    def test_finds_boundary_valid_in_range(self, mock_tokenizer):
        msgs = [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "q2"},
            {"role": "assistant", "content": "a2"},
        ]
        mock_tokenizer.count_one.return_value = 1
        idx = _find_round_boundary_at_token(msgs, mock_tokenizer, target=3, min_keep=1)
        assert idx >= 0
        assert idx <= len(msgs)

    def test_returns_zero_when_no_boundary_found(self, mock_tokenizer):
        msgs = [{"role": "assistant", "content": "a1"}]
        mock_tokenizer.count_one.return_value = 100
        idx = _find_round_boundary_at_token(msgs, mock_tokenizer, target=1, min_keep=1)
        assert idx == 0
