import sys
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))
import neo_code
from conftest import FakeChunk, FakeChoice, FakeDelta, FakeToolCall, FakeFunction, FakeUsage


def _make_chunk(reasoning=None, tool_calls=None, content=None, usage=None):
    delta = FakeDelta(
        reasoning_content=reasoning,
        content=content,
        tool_calls=tool_calls,
    )
    choice = FakeChoice(delta)
    return FakeChunk(choices=[choice], usage=usage)


def _fake_state():
    s = neo_code.SessionState()
    s.interrupted = False
    return s


class TestProcessStreamBasic:
    def test_simple_content(self):
        state = _fake_state()
        chunks = [
            _make_chunk(content="Hello "),
            _make_chunk(content="World"),
        ]
        reasoning, content, tool_calls, usage, finish_reason = neo_code.process_stream(state, iter(chunks))
        assert content == "Hello World"
        assert reasoning == ""
        assert tool_calls == {}

    def test_reasoning_content(self):
        state = _fake_state()
        chunks = [
            _make_chunk(reasoning="Let me think..."),
            _make_chunk(reasoning=" more"),
            _make_chunk(content="Answer"),
        ]
        reasoning, content, tool_calls, usage, finish_reason = neo_code.process_stream(state, iter(chunks))
        assert "Let me think..." in reasoning
        assert "more" in reasoning
        assert content == "Answer"

    def test_usage_captured(self):
        state = _fake_state()
        usage = FakeUsage(total_tokens=500)
        chunks = [
            _make_chunk(content="Hi"),
            FakeChunk(choices=[], usage=usage),
        ]
        _, _, _, u, _ = neo_code.process_stream(state, iter(chunks))
        assert u is not None
        assert u.total_tokens == 500

    def test_interrupt_stops_stream(self):
        state = _fake_state()
        chunks = [
            _make_chunk(content="Part 1"),
            _make_chunk(content="Part 2"),
        ]
        state.interrupted = True
        _, content, _, _, _ = neo_code.process_stream(state, iter(chunks))
        assert content == ""

    def test_length_finish_with_complete_content_no_warning(self, caplog):
        state = _fake_state()
        chunks = [
            _make_chunk(content="这是一句完整的话。"),
            FakeChunk(choices=[FakeChoice(finish_reason="length")]),
        ]
        with caplog.at_level("WARNING", logger="neo_code"):
            _, content, _, _, fr = neo_code.process_stream(state, iter(chunks))
        assert fr == "length"
        assert content == "这是一句完整的话。"
        assert "truncated" not in caplog.text.lower()

    def test_length_finish_with_cut_content_warns(self, caplog):
        state = _fake_state()
        chunks = [
            _make_chunk(content="这句话没有说完，后面还"),
            FakeChunk(choices=[FakeChoice(finish_reason="length")]),
        ]
        with caplog.at_level("WARNING", logger="neo_code"):
            neo_code.process_stream(state, iter(chunks))
        assert "truncated" in caplog.text.lower()


class TestLooksTruncated:
    def test_complete_endings_not_truncated(self):
        for text in ("完整。", "完整！", "完整吗？", "未完待续…", "```", "结束)"):
            assert neo_code._looks_truncated(text) is False, text

    def test_cut_endings_truncated(self):
        for text in ("这句话没说完", "末尾被切断的", "a b c"):
            assert neo_code._looks_truncated(text) is True, text


class TestProcessStreamToolCalls:
    def test_tool_call_split_across_chunks(self):
        state = _fake_state()
        full_args = json.dumps({"path": "/etc/passwd", "offset": 0, "limit": 2000})
        chunks = [
            _make_chunk(tool_calls=[FakeToolCall(index=0, id="call_abc123")]),
            _make_chunk(tool_calls=[FakeToolCall(index=0, function=FakeFunction(name="read_file"))]),
            _make_chunk(tool_calls=[FakeToolCall(index=0, function=FakeFunction(arguments=full_args[:10]))]),
            _make_chunk(tool_calls=[FakeToolCall(index=0, function=FakeFunction(arguments=full_args[10:30]))]),
            _make_chunk(tool_calls=[FakeToolCall(index=0, function=FakeFunction(arguments=full_args[30:]))]),
        ]
        _, _, tool_calls, _, _ = neo_code.process_stream(state, iter(chunks))
        assert 0 in tool_calls
        assert tool_calls[0]["id"] == "call_abc123"
        assert tool_calls[0]["name"] == "read_file"
        parsed = json.loads(tool_calls[0]["arguments"])
        assert parsed == {"path": "/etc/passwd", "offset": 0, "limit": 2000}

    def test_multiple_tools_interleaved(self):
        state = _fake_state()
        chunks = [
            _make_chunk(tool_calls=[FakeToolCall(index=0, id="call_1", function=FakeFunction(name="read_file"))]),
            _make_chunk(tool_calls=[FakeToolCall(index=1, id="call_2", function=FakeFunction(name="grep_search"))]),
            _make_chunk(tool_calls=[FakeToolCall(index=0, function=FakeFunction(arguments='{"path":"/a"}'))]),
            _make_chunk(tool_calls=[FakeToolCall(index=1, function=FakeFunction(arguments='{"pattern":"foo"}'))]),
        ]
        _, _, tool_calls, _, _ = neo_code.process_stream(state, iter(chunks))
        assert tool_calls[0]["name"] == "read_file"
        assert tool_calls[1]["name"] == "grep_search"
        assert json.loads(tool_calls[0]["arguments"]) == {"path": "/a"}
        assert json.loads(tool_calls[1]["arguments"]) == {"pattern": "foo"}

    def test_reasoning_and_tool_calls_interleaved(self):
        state = _fake_state()
        chunks = [
            _make_chunk(reasoning="Let me think..."),
            _make_chunk(tool_calls=[FakeToolCall(index=0, id="call_x")]),
            _make_chunk(reasoning="more thinking..."),
            _make_chunk(tool_calls=[FakeToolCall(index=0, function=FakeFunction(name="read_file", arguments='{}'))]),
        ]
        reasoning, _, tool_calls, _, _ = neo_code.process_stream(state, iter(chunks))
        assert "Let me think..." in reasoning
        assert "more thinking..." in reasoning
        assert tool_calls[0]["name"] == "read_file"

    def test_empty_tool_calls_no_name(self):
        state = _fake_state()
        chunks = [
            _make_chunk(tool_calls=[FakeToolCall(index=0, id="call_y")]),
            _make_chunk(tool_calls=[FakeToolCall(index=0)]),
            _make_chunk(tool_calls=[FakeToolCall(index=0, function=FakeFunction(name="run_command", arguments='{"command":"ls"}'))]),
        ]
        _, _, tool_calls, _, _ = neo_code.process_stream(state, iter(chunks))
        assert tool_calls[0]["name"] == "run_command"
        assert json.loads(tool_calls[0]["arguments"]) == {"command": "ls"}


class TestFormatToolCalls:
    def test_format_single(self):
        tool_calls = {0: {"id": "call_1", "name": "read_file", "arguments": '{"path":"/a"}'}}
        result = neo_code._format_tool_calls(tool_calls)
        assert len(result) == 1
        assert result[0]["id"] == "call_1"
        assert result[0]["function"]["name"] == "read_file"

    def test_format_multiple_sorted(self):
        tool_calls = {
            1: {"id": "call_2", "name": "grep_search", "arguments": "{}"},
            0: {"id": "call_1", "name": "read_file", "arguments": "{}"},
        }
        result = neo_code._format_tool_calls(tool_calls)
        assert result[0]["id"] == "call_1"
        assert result[1]["id"] == "call_2"


class TestSanitizeMessages:
    def test_removes_orphan_tool_messages(self):
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "tool", "tool_call_id": "orphan_id", "content": "result"},
        ]
        result = neo_code.sanitize_messages(msgs)
        assert len(result) == 1
        assert result[0]["role"] == "user"

    def test_keeps_valid_tool_messages(self):
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "call_1", "function": {"name": "read_file", "arguments": "{}"}}
            ]},
            {"role": "tool", "tool_call_id": "call_1", "content": "result"},
        ]
        result = neo_code.sanitize_messages(msgs)
        assert len(result) == 3


class TestAgentLoopAutoContinue:
    """finish_reason=length 且正文真的被切断时，agent_loop 应同轮自动续写，
    而不是要求用户手动输入“继续”。"""

    def _text_stream(self, text, finish_reason="stop"):
        return iter([
            FakeChunk(choices=[FakeChoice(FakeDelta(content=text), finish_reason=finish_reason)])
        ])

    def _setup(self, streams):
        state = _fake_state()
        client = MagicMock()
        client.smart_route_chat.side_effect = streams
        client.model = "deepseek-v4-pro"
        client.flash_model = "deepseek-v4-flash"
        tokenizer = MagicMock()
        tokenizer.count.return_value = 100
        tokenizer.count_one.return_value = 10
        cm = MagicMock()
        safety = MagicMock()
        safety.check.return_value = ("approve", "ok")
        messages = []
        patchers = [
            patch.object(neo_code, "maybe_summarize",
                         side_effect=lambda state, messages, tokenizer, client: messages),
            patch.object(neo_code, "_build_status_bar", return_value=""),
            patch.object(neo_code, "generate_schemas", return_value=[]),
        ]
        for p in patchers:
            p.start()
        return state, client, tokenizer, cm, safety, messages, patchers

    def test_truncated_text_auto_continues(self):
        streams = [
            self._text_stream("这句话没有说完，后面还", finish_reason="length"),
            self._text_stream("有后续内容，现在完整了。", finish_reason="stop"),
        ]
        state, client, tokenizer, cm, safety, messages, patchers = self._setup(streams)
        try:
            result = neo_code.agent_loop(
                state, "hi", messages, client, safety, tokenizer, cm, thinking=False
            )
        finally:
            for p in patchers:
                p.stop()
        assert client.smart_route_chat.call_count == 2
        last = result[-1]
        assert last["role"] == "assistant"
        assert "这句话没有说完，后面还\n有后续内容，现在完整了。" in last["content"]
        assert "输入" not in last["content"]
        cm.save.assert_called()

    def test_still_truncated_after_auto_continue_keeps_hint(self):
        streams = [
            self._text_stream("第一段没写完", finish_reason="length"),
            self._text_stream("第二段也断了", finish_reason="length"),
            self._text_stream("第三段还是断了", finish_reason="length"),
            self._text_stream("第四段断了", finish_reason="length"),
        ]
        state, client, tokenizer, cm, safety, messages, patchers = self._setup(streams)
        try:
            result = neo_code.agent_loop(
                state, "hi", messages, client, safety, tokenizer, cm, thinking=False
            )
        finally:
            for p in patchers:
                p.stop()
        # 1 次原始回复 + MAX_AUTO_CONTINUE_ROUNDS 次自动续写
        assert client.smart_route_chat.call_count == 1 + neo_code.MAX_AUTO_CONTINUE_ROUNDS
        last = result[-1]
        assert "仍超出单次输出上限" in last["content"]

    def test_complete_text_no_extra_call(self):
        streams = [self._text_stream("回复完整。", finish_reason="stop")]
        state, client, tokenizer, cm, safety, messages, patchers = self._setup(streams)
        try:
            result = neo_code.agent_loop(
                state, "hi", messages, client, safety, tokenizer, cm, thinking=False
            )
        finally:
            for p in patchers:
                p.stop()
        assert client.smart_route_chat.call_count == 1
        assert result[-1]["content"] == "回复完整。"


class TestAgentLoopToolNudge:
    """工具后停顿行为：沉默或工具失败/截断才自动补“继续”（文本收尾不触发，省 API 调用）。"""

    def _text_stream(self, text, finish_reason="stop"):
        return iter([
            FakeChunk(choices=[FakeChoice(FakeDelta(content=text), finish_reason=finish_reason)])
        ])

    def _tool_stream(self, name="run_command", args='{"command":"echo hi"}'):
        chunks = [
            _make_chunk(tool_calls=[FakeToolCall(index=0, id="call_t1")]),
            _make_chunk(tool_calls=[FakeToolCall(index=0, function=FakeFunction(name=name))]),
            _make_chunk(tool_calls=[FakeToolCall(index=0, function=FakeFunction(arguments=args))]),
        ]
        return iter(chunks)

    def _setup(self, streams):
        state = _fake_state()
        client = MagicMock()
        client.smart_route_chat.side_effect = streams
        client.model = "deepseek-v4-pro"
        client.flash_model = "deepseek-v4-flash"
        tokenizer = MagicMock()
        tokenizer.count.return_value = 100
        tokenizer.count_one.return_value = 10
        cm = MagicMock()
        safety = MagicMock()
        safety.check.return_value = ("approve", "ok")
        messages = []
        patchers = [
            patch.object(neo_code, "maybe_summarize",
                         side_effect=lambda state, messages, tokenizer, client: messages),
            patch.object(neo_code, "_build_status_bar", return_value=""),
            patch.object(neo_code, "generate_schemas", return_value=[]),
            patch.object(neo_code, "_execute_tool_safe", return_value="OK mock"),
        ]
        for p in patchers:
            p.start()
        return state, client, tokenizer, cm, safety, messages, patchers

    def test_text_stop_after_tool_round_no_nudge(self):
        # 工具成功 + 文本收尾（finish_reason=stop）：不再自动补“继续”，避免每回合多一次 API 调用
        streams = [
            self._tool_stream(),
            self._text_stream("第一段说明。"),
        ]
        state, client, tokenizer, cm, safety, messages, patchers = self._setup(streams)
        try:
            result = neo_code.agent_loop(
                state, "hi", messages, client, safety, tokenizer, cm, thinking=False
            )
        finally:
            for p in patchers:
                p.stop()
        assert client.smart_route_chat.call_count == 2
        assert len([m for m in result if m["role"] == "tool"]) == 1
        assert result[-1]["content"] == "第一段说明。"

    def test_empty_after_tool_round_triggers_nudge(self):
        streams = [
            self._tool_stream(),
            self._text_stream(""),
            self._text_stream("继续把剩下的做完。"),
        ]
        state, client, tokenizer, cm, safety, messages, patchers = self._setup(streams)
        try:
            result = neo_code.agent_loop(
                state, "hi", messages, client, safety, tokenizer, cm, thinking=False
            )
        finally:
            for p in patchers:
                p.stop()
        assert client.smart_route_chat.call_count == 3
        assert result[-1]["content"] == "继续把剩下的做完。"

    def test_no_nudge_without_tool_round(self):
        streams = [self._text_stream("直接回答。")]
        state, client, tokenizer, cm, safety, messages, patchers = self._setup(streams)
        try:
            result = neo_code.agent_loop(
                state, "hi", messages, client, safety, tokenizer, cm, thinking=False
            )
        finally:
            for p in patchers:
                p.stop()
        assert client.smart_route_chat.call_count == 1
        assert result[-1]["content"] == "直接回答。"

    def test_nudge_response_with_tools_is_executed(self):
        # 工具后沉默 → nudge 返回工具调用 → 继续执行直到完成
        streams = [
            self._tool_stream(),
            self._text_stream(""),
            self._tool_stream(name="read_file", args='{"path":"x"}'),
            self._text_stream("最终完成。"),
        ]
        state, client, tokenizer, cm, safety, messages, patchers = self._setup(streams)
        try:
            result = neo_code.agent_loop(
                state, "hi", messages, client, safety, tokenizer, cm, thinking=False
            )
        finally:
            for p in patchers:
                p.stop()
        assert client.smart_route_chat.call_count == 4
        tool_msgs = [m for m in result if m["role"] == "tool"]
        assert len(tool_msgs) == 2
        assert result[-1]["content"] == "最终完成。"

    def test_nudge_happens_at_most_once_per_turn(self):
        # 工具后两次沉默：只触发一次 nudge，第二次沉默触发“空回复两次”兜底
        streams = [
            self._tool_stream(),
            self._text_stream(""),
            self._text_stream(""),
            self._text_stream(""),
        ]
        state, client, tokenizer, cm, safety, messages, patchers = self._setup(streams)
        try:
            result = neo_code.agent_loop(
                state, "hi", messages, client, safety, tokenizer, cm, thinking=False
            )
        finally:
            for p in patchers:
                p.stop()
        assert client.smart_route_chat.call_count == 4
        assert result[-1]["content"] == "[Agent produced empty response twice. Please rephrase your request.]"
