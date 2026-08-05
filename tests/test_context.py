import sys
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))
import neo_code


class TestTokenCounter:
    def test_count_basic(self):
        tc = neo_code.TokenCounter()
        count = tc._count("Hello world")
        assert count > 0

    def test_count_chinese(self):
        tc = neo_code.TokenCounter()
        count = tc._count("你好世界")
        assert count > 0

    def test_count_empty(self):
        tc = neo_code.TokenCounter()
        count = tc._count("")
        assert count == 0

    def test_count_one_message(self):
        tc = neo_code.TokenCounter()
        msg = {"role": "user", "content": "Hello"}
        count = tc.count_one(msg)
        assert count > 0

    def test_count_messages_list(self):
        tc = neo_code.TokenCounter()
        msgs = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
        ]
        total = tc.count(msgs)
        assert total > 0


class TestMicroCompact:
    def test_short_content_unchanged(self):
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "tool", "content": "short result"},
        ]
        result = neo_code.enhanced_compact(msgs, max_result_len=2000)
        assert result[1]["content"] == "short result"

    def test_long_content_compacted(self):
        long_content = "x" * 5000
        msgs = [
            {"role": "tool", "content": long_content},
        ]
        result = neo_code.enhanced_compact(msgs, max_result_len=2000)
        assert len(result[0]["content"]) < len(long_content)
        assert "<result" in result[0]["content"]
        assert "omitted" in result[0]["content"]

    def test_non_tool_messages_unchanged(self):
        msgs = [
            {"role": "user", "content": "x" * 5000},
            {"role": "assistant", "content": "x" * 5000},
        ]
        result = neo_code.enhanced_compact(msgs, max_result_len=2000)
        assert result[0]["content"] == "x" * 5000
        assert result[1]["content"] == "x" * 5000


class TestCheckSingleToolResultSize:
    def test_normal_size_passes(self):
        content = "x" * 1000
        result = neo_code._check_single_tool_result_size(content)
        assert result == content

    def test_oversized_truncated(self):
        content = "x" * 200_000
        result = neo_code._check_single_tool_result_size(content, max_chars=100_000)
        assert len(result) < len(content)
        assert "too large" in result.lower()


class TestMaybeSummarize:
    def test_no_summary_below_threshold(self, state, mock_client, mock_tokenizer):
        mock_tokenizer.count.return_value = 100
        msgs = [{"role": "user", "content": "hi"}]
        result = neo_code.maybe_summarize(state, msgs, mock_tokenizer, mock_client)
        assert result == msgs or len(result) >= len(msgs)

    def test_micro_compact_applied(self, state, mock_client, mock_tokenizer):
        mock_tokenizer.count.return_value = 100
        long_content = "x" * 5000
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "tool", "content": long_content},
        ]
        # 纯函数直接验证：超过 MICRO_COMPACT_LIMIT 的 tool 结果会被压缩
        compressed = neo_code._compress_one(long_content)
        assert len(compressed) < len(long_content)
        # maybe_summarize 低于阈值时返回原列表（发送视图压缩不写回 canonical）
        result = neo_code.maybe_summarize(state, msgs, mock_tokenizer, mock_client)
        assert result == msgs


class TestFindRoundBoundary:
    def test_finds_boundary(self, mock_tokenizer):
        mock_tokenizer.count_one.return_value = 10
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "reply1"},
            {"role": "user", "content": "msg2"},
            {"role": "assistant", "content": "reply2"},
            {"role": "user", "content": "msg3"},
            {"role": "assistant", "content": "reply3"},
        ]
        idx = neo_code._find_round_boundary_at_token(msgs, mock_tokenizer, 100, 2)
        assert idx > 0

    def test_no_boundary_for_short(self, mock_tokenizer):
        mock_tokenizer.count_one.return_value = 1
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        idx = neo_code._find_round_boundary_at_token(msgs, mock_tokenizer, 1000000, 5)
        assert idx == 0
