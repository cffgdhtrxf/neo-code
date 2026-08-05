import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import neo_code
from neo_code import ConversationManager, HISTORY_DIR, HISTORY_FILE, HISTORY_BAK


class TestConversationManager:
    def test_save_and_load_basic(self, tmp_path):
        cm = ConversationManager()
        messages = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
        with patch.object(neo_code, "HISTORY_FILE", tmp_path / "history.json"):
            with patch.object(neo_code, "HISTORY_BAK", tmp_path / "history.json.bak"):
                cm.save(messages)
                loaded = cm.load()
                assert loaded == messages

    def test_load_from_empty_dir(self):
        cm = ConversationManager()
        with patch.object(neo_code, "HISTORY_FILE", Path("/nonexistent/history.json")):
            result = cm.load()
            assert result is None

    def test_load_corrupted_json(self, tmp_path):
        hf = tmp_path / "history.json"
        hf.write_text("not valid json{{{", encoding="utf-8")
        cm = ConversationManager()
        with patch.object(neo_code, "HISTORY_FILE", hf):
            with patch.object(neo_code, "HISTORY_BAK", tmp_path / "nonexistent.bak"):
                result = cm.load()
                assert result is None

    def test_load_falls_back_to_bak(self, tmp_path):
        hf = tmp_path / "history.json"
        hf.write_text("corrupted", encoding="utf-8")
        bak = tmp_path / "history.json.bak"
        bak.write_text(json.dumps([{"role": "user", "content": "from_bak"}]), encoding="utf-8")
        cm = ConversationManager()
        with patch.object(neo_code, "HISTORY_FILE", hf):
            with patch.object(neo_code, "HISTORY_BAK", bak):
                result = cm.load()
                assert result == [{"role": "user", "content": "from_bak"}]

    def test_load_dict_format(self, tmp_path):
        hf = tmp_path / "history.json"
        data = {"messages": [{"role": "user", "content": "dict_format"}], "saved_at": "2026-01-01"}
        hf.write_text(json.dumps(data), encoding="utf-8")
        cm = ConversationManager()
        with patch.object(neo_code, "HISTORY_FILE", hf):
            with patch.object(neo_code, "HISTORY_BAK", tmp_path / "nonexistent.bak"):
                result = cm.load()
                assert result == [{"role": "user", "content": "dict_format"}]

    def test_save_creates_bak(self, tmp_path):
        hf = tmp_path / "history.json"
        bak = tmp_path / "history.json.bak"
        messages1 = [{"role": "user", "content": "first"}]
        messages2 = [{"role": "user", "content": "second"}]
        cm = ConversationManager()
        with patch.object(neo_code, "HISTORY_FILE", hf):
            with patch.object(neo_code, "HISTORY_BAK", bak):
                cm.save(messages1)
                cm.save(messages2)
                assert bak.is_file()
                loaded = cm.load()
                assert loaded == messages2

    def test_save_truncates_large_content(self, tmp_path):
        hf = tmp_path / "history.json"
        huge_messages = [{"role": "user", "content": "x" * 100}] * 300
        bak = tmp_path / "history.json.bak"
        cm = ConversationManager()
        with patch.object(neo_code, "HISTORY_FILE", hf):
            with patch.object(neo_code, "HISTORY_BAK", bak):
                with patch("neo_code.MAX_HISTORY_SIZE", 5000):
                    cm.save(huge_messages)
                    loaded = cm.load()
                    assert len(loaded) <= 50

    def test_crash_recovery_save_and_recover(self, tmp_path):
        dump_path = tmp_path / "crash_dump.json"
        messages = [{"role": "user", "content": "crash_test"}]
        with patch.object(neo_code, "CRASH_DUMP_PATH", dump_path):
            neo_code.enable_crash_recovery(messages)
            assert not dump_path.exists()
            recovered = neo_code.recover_crash()
            assert recovered is None

            dump_path.write_text(json.dumps({
                "timestamp": datetime.now().isoformat(),
                "message_count": 1,
                "messages": messages
            }), encoding="utf-8")
            recovered = neo_code.recover_crash()
            assert recovered == messages
            assert not dump_path.exists()

    def test_crash_recovery_no_file(self):
        with patch.object(neo_code, "CRASH_DUMP_PATH", Path("/nonexistent/dump.json")):
            result = neo_code.recover_crash()
            assert result is None
