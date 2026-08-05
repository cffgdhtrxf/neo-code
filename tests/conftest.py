import sys
import os
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import neo_code


class FakeDelta:
    def __init__(self, reasoning_content=None, content=None, tool_calls=None):
        self.reasoning_content = reasoning_content
        self.content = content
        self.tool_calls = tool_calls


class FakeChoice:
    def __init__(self, delta=None, finish_reason=None):
        self.delta = delta or FakeDelta()
        self.finish_reason = finish_reason


class FakeChunk:
    def __init__(self, choices=None, usage=None):
        self.choices = choices or []
        self.usage = usage


class FakeToolCall:
    def __init__(self, index=0, id=None, function=None):
        self.index = index
        self.id = id
        self.function = function


class FakeFunction:
    def __init__(self, name=None, arguments=None):
        self.name = name
        self.arguments = arguments


class FakeUsage:
    def __init__(self, total_tokens=100, prompt_tokens=80, completion_tokens=20):
        self.total_tokens = total_tokens
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.prompt_tokens_details = None
        self.completion_tokens_details = None


@pytest.fixture
def state():
    return neo_code.SessionState()


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.model = "deepseek-v4-pro"
    client.flash_model = "deepseek-v4-flash"
    client.flash_chat.return_value = "SAFE"
    client.chat_stream.return_value = iter([
        FakeChunk(choices=[FakeChoice(FakeDelta(content="Hello!"))])
    ])
    return client


@pytest.fixture
def mock_tokenizer():
    tc = MagicMock()
    tc.count.return_value = 100
    tc.count_one.return_value = 10
    tc._count.return_value = 10
    return tc


@pytest.fixture
def sample_file(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("Hello World\nLine 2\nLine 3\n", encoding="utf-8")
    return f


@pytest.fixture
def sample_json(tmp_path):
    f = tmp_path / "test.json"
    f.write_text('{"key": "value"}', encoding="utf-8")
    return f
