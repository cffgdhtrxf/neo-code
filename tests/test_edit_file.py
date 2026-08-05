import sys
import os
import pytest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
import neo_code


class TestEditFileBasic:
    def test_no_change_needed(self, state, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world", encoding="utf-8")
        neo_code.set_edit_confirm_mode("never")
        result = neo_code.tool_edit_file(state, str(f), "hello", "hello")
        assert "no change" in result.lower()

    def test_single_match_replace(self, state, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world\nfoo bar\n", encoding="utf-8")
        neo_code._mark_file_read(f)
        neo_code.set_edit_confirm_mode("never")
        result = neo_code.tool_edit_file(state, str(f), "hello world", "goodbye world")
        assert "OK" in result
        assert "goodbye world" in f.read_text(encoding="utf-8")

    def test_file_not_found(self, state, tmp_path):
        neo_code.set_edit_confirm_mode("never")
        result = neo_code.tool_edit_file(state, str(tmp_path / "nonexistent.txt"), "a", "b")
        assert "Error" in result

    def test_old_text_not_found(self, state, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world", encoding="utf-8")
        neo_code._mark_file_read(f)
        neo_code.set_edit_confirm_mode("never")
        result = neo_code.tool_edit_file(state, str(f), "xyz", "abc")
        assert "Error" in result
        assert "未找到" in result

    def test_multiple_matches(self, state, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello\nhello\nhello\n", encoding="utf-8")
        neo_code._mark_file_read(f)
        neo_code.set_edit_confirm_mode("never")
        result = neo_code.tool_edit_file(state, str(f), "hello", "world")
        assert "Error" in result
        assert "出现 3 处" in result
        assert "replace_all" in result


class TestEditFileCRLF:
    def test_crlf_normalization(self, state, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("line1\r\nline2\r\nline3\r\n", encoding="utf-8")
        neo_code._mark_file_read(f)
        neo_code.set_edit_confirm_mode("never")
        result = neo_code.tool_edit_file(state, str(f), "line2", "modified")
        assert "OK" in result
        content = f.read_text(encoding="utf-8")
        assert "modified" in content

    def test_crlf_preserved(self, state, tmp_path):
        f = tmp_path / "test.txt"
        original = "line1\r\nline2\r\nline3\r\n"
        f.write_bytes(original.encode("utf-8"))
        neo_code.set_edit_confirm_mode("never")
        neo_code.tool_edit_file(state, str(f), "line2", "modified")
        content = f.read_bytes()
        assert b"\r\n" in content


class TestEditFileBackup:
    def test_backup_created_and_removed(self, state, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world", encoding="utf-8")
        bak = f.with_suffix(f.suffix + '.bak')
        neo_code.set_edit_confirm_mode("never")
        neo_code.tool_edit_file(state, str(f), "hello", "goodbye")
        assert not bak.exists()

    def test_backup_restored_on_error(self, state, tmp_path):
        f = tmp_path / "test.txt"
        original = "hello world"
        f.write_text(original, encoding="utf-8")
        neo_code.set_edit_confirm_mode("never")
        with patch.object(neo_code, 'atomic_write', side_effect=Exception("write error")):
            result = neo_code.tool_edit_file(state, str(f), "hello", "goodbye")
        assert "backup restored" in result.lower() or "Error" in result
        assert f.read_text(encoding="utf-8") == original


class TestEditFileUnicode:
    def test_unicode_content(self, state, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("你好世界\nHello\n", encoding="utf-8")
        neo_code._mark_file_read(f)
        neo_code.set_edit_confirm_mode("never")
        result = neo_code.tool_edit_file(state, str(f), "你好世界", "世界你好")
        assert "OK" in result
        assert "世界你好" in f.read_text(encoding="utf-8")

    def test_emoji_content(self, state, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("Hello 🌍 World\n", encoding="utf-8")
        neo_code._mark_file_read(f)
        neo_code.set_edit_confirm_mode("never")
        result = neo_code.tool_edit_file(state, str(f), "Hello 🌍 World", "Hello 🌎 Earth")
        assert "OK" in result


class TestEditFileCache:
    def test_cache_invalidated_after_edit(self, state, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("original content", encoding="utf-8")
        neo_code.cached_read(state, f)
        neo_code._mark_file_read(f)
        assert str(f.resolve()) in state.file_cache
        neo_code.set_edit_confirm_mode("never")
        neo_code.tool_edit_file(state, str(f), "original", "modified")
        assert str(f.resolve()) not in state.file_cache
