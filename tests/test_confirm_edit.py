import pytest
from unittest.mock import patch

import neo_code
from neo_code import _confirm_edit, _edit_confirm_mode, set_edit_confirm_mode


class TestConfirmEdit:
    def teardown_method(self):
        set_edit_confirm_mode("auto")

    def test_mode_never_auto_approves(self, tmp_path):
        set_edit_confirm_mode("never")
        f = tmp_path / "test.py"
        f.write_text("content", encoding="utf-8")
        assert _confirm_edit(str(f)) is True

    def test_mode_always_prompts_and_denies_by_default(self, tmp_path):
        set_edit_confirm_mode("always")
        f = tmp_path / "test.py"
        f.write_text("content", encoding="utf-8")

        with patch.object(neo_code, "_safe_input", return_value="n"):
            with patch("sys.stdout.isatty", return_value=True):
                assert _confirm_edit(str(f)) is False

    def test_mode_always_prompts_and_approves_with_y(self, tmp_path):
        set_edit_confirm_mode("always")
        f = tmp_path / "test.py"
        f.write_text("content", encoding="utf-8")

        with patch.object(neo_code, "_safe_input", return_value="y"):
            with patch("sys.stdout.isatty", return_value=True):
                assert _confirm_edit(str(f)) is True

    def test_mode_always_non_tty_denies(self, tmp_path):
        set_edit_confirm_mode("always")
        f = tmp_path / "test.py"
        f.write_text("content", encoding="utf-8")

        with patch("sys.stdout.isatty", return_value=False):
            assert _confirm_edit(str(f)) is False

    def test_mode_ask_prompts_same_as_always(self, tmp_path):
        set_edit_confirm_mode("ask")
        f = tmp_path / "test.py"
        f.write_text("content", encoding="utf-8")

        with patch.object(neo_code, "_safe_input", return_value="y"):
            with patch("sys.stdout.isatty", return_value=True):
                assert _confirm_edit(str(f)) is True

    def test_mode_auto_non_tty_checks_approved_paths(self, tmp_path):
        set_edit_confirm_mode("auto")
        f = tmp_path / "test.py"

        with patch("sys.stdout.isatty", return_value=False):
            with patch.dict(neo_code.CONFIG, {
                "cli_mode": {"auto_approve_write_in": [str(tmp_path)]}
            }, clear=False):
                assert _confirm_edit(str(f)) is True

    def test_mode_auto_non_tty_empty_approved_denies(self, tmp_path):
        set_edit_confirm_mode("auto")
        f = tmp_path / "test.py"

        with patch("sys.stdout.isatty", return_value=False):
            with patch.dict(neo_code.CONFIG, {
                "cli_mode": {"auto_approve_write_in": []}
            }, clear=False):
                assert _confirm_edit(str(f)) is False

    def test_mode_denyskip_approved_path_passes(self, tmp_path):
        set_edit_confirm_mode("denyskip")
        f = tmp_path / "test.py"

        with patch.dict(neo_code.CONFIG, {
            "cli_mode": {"auto_approve_write_in": [str(tmp_path)]}
        }, clear=False):
            assert _confirm_edit(str(f)) is True

    def test_mode_denyskip_unapproved_denies(self, tmp_path):
        set_edit_confirm_mode("denyskip")
        f = tmp_path / "test.py"

        with patch.dict(neo_code.CONFIG, {
            "cli_mode": {"auto_approve_write_in": []}
        }, clear=False):
            assert _confirm_edit(str(f)) is False


class TestResolveConfirmMode:
    def test_always(self):
        assert neo_code.resolve_confirm_mode("always", True) == "always"

    def test_never(self):
        assert neo_code.resolve_confirm_mode("never", False) == "never"

    def test_interactive_returns_ask(self):
        assert neo_code.resolve_confirm_mode("auto", True) == "ask"

    def test_non_interactive_returns_never(self):
        # 非交互不再询问（denyskip 已废弃）：是否放行交给 SafetyGate 门禁
        assert neo_code.resolve_confirm_mode("auto", False) == "never"
