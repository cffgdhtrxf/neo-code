import sys
import os
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))
import neo_code


class TestNormalizePath:
    def test_absolute_path(self):
        if sys.platform == "win32":
            p = neo_code.normalize_path("C:\\Users\\test")
        else:
            p = neo_code.normalize_path("/usr/local/bin")
        assert p.is_absolute()

    def test_relative_path_resolved(self):
        p = neo_code.normalize_path("test.txt")
        assert p.is_absolute()
        assert str(Path.cwd()) in str(p)

    def test_tilde_expansion(self):
        p = neo_code.normalize_path("~/test")
        assert "~" not in str(p)
        assert str(Path.home()) in str(p)

    def test_dot_resolution(self):
        p = neo_code.normalize_path(".")
        assert p == Path.cwd().resolve()


class TestBuildShellCommand:
    def test_returns_list(self):
        cmd = neo_code.build_shell_command("echo hello")
        assert isinstance(cmd, list)
        assert len(cmd) >= 2

    def test_shell_available(self):
        cmd = neo_code.build_shell_command("ls")
        shell = cmd[0]
        assert shell in ("bash", "pwsh", "powershell", "cmd")

    def test_command_included(self):
        cmd = neo_code.build_shell_command("echo test")
        assert any("echo test" in str(part) for part in cmd)

    def test_windows_utf8_encoding_prefix(self):
        if sys.platform != "win32":
            pytest.skip("Windows only")
        cmd = neo_code.build_shell_command("echo test")
        if cmd[0] in ("pwsh", "powershell"):
            assert "[Console]::OutputEncoding" in cmd[-1]
        elif cmd[0] == "cmd":
            assert "chcp 65001" in cmd[-1]


class TestEnvironmentCheck:
    def test_check_environment_does_not_raise_and_reports_shell(self, monkeypatch):
        # 避免真实网络依赖：离线时 Network 项也应被捕获为失败而非异常
        def fake_conn(addr, timeout):
            raise OSError("offline")

        monkeypatch.setattr(neo_code.socket, "create_connection", fake_conn)
        results = neo_code.check_environment()
        labels = [r[0] for r in results]
        assert any(label.startswith("Shell:") for label in labels)
        assert any(label.startswith("Working directory:") for label in labels)


class TestSafeDecode:
    def test_utf8_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("Hello 你好", encoding="utf-8")
        result = neo_code.safe_decode(f)
        assert "Hello 你好" in result

    def test_binary_file_fallback(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"\x80\x81\x82\x83")
        result = neo_code.safe_decode(f)
        assert isinstance(result, str)


class TestAtomicWrite:
    def test_write_creates_file(self, tmp_path):
        f = tmp_path / "test.txt"
        neo_code.atomic_write(f, "hello world")
        assert f.read_text(encoding="utf-8") == "hello world"

    def test_write_overwrites(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("old", encoding="utf-8")
        neo_code.atomic_write(f, "new")
        assert f.read_text(encoding="utf-8") == "new"

    def test_write_creates_parents(self, tmp_path):
        f = tmp_path / "sub" / "dir" / "test.txt"
        neo_code.atomic_write(f, "content")
        assert f.exists()

    def test_no_tmp_file_left(self, tmp_path):
        f = tmp_path / "test.txt"
        neo_code.atomic_write(f, "content")
        tmp = f.with_suffix(f.suffix + '.tmp')
        assert not tmp.exists()


class TestIsProtectedPath:
    def test_windows_system_protected(self):
        if sys.platform == "win32":
            assert neo_code.is_protected_path(Path("C:/Windows/System32"))
        else:
            assert neo_code.is_protected_path(Path("/etc/passwd"))

    def test_normal_path_not_protected(self, tmp_path):
        assert not neo_code.is_protected_path(tmp_path / "test.txt")


class TestTruncateOutput:
    def test_short_unchanged(self):
        text = "short text"
        assert neo_code.truncate_output(text, max_len=100) == text

    def test_long_truncated(self):
        text = "x" * 10000
        result = neo_code.truncate_output(text, max_len=1000)
        assert len(result) < len(text)
        assert "omitted" in result


class TestSessionState:
    def test_initial_state(self):
        s = neo_code.SessionState()
        assert s.interrupted is False
        assert s.subagent_depth == 0
        assert s.tavily_monthly_count == 0
        assert s.consecutive_denials == 0

    def test_interrupt_single(self):
        s = neo_code.SessionState()
        result = s.signal_interrupt()
        assert result is False
        assert s.interrupted is True

    def test_interrupt_double(self):
        s = neo_code.SessionState()
        s.signal_interrupt()
        result = s.signal_interrupt()
        assert result is True

    def test_reset_interrupt(self):
        s = neo_code.SessionState()
        s.signal_interrupt()
        s.reset_interrupt()
        assert s.interrupted is False
        assert s._interrupt_count == 0

    def test_subagent_depth(self):
        s = neo_code.SessionState()
        s.enter_subagent()
        s.enter_subagent()
        assert s.subagent_depth == 2
        s.leave_subagent()
        assert s.subagent_depth == 1

    def test_tavily_monthly_reset(self):
        s = neo_code.SessionState()
        s.inc_tavily()
        assert s.tavily_monthly_count == 1
        s.inc_tavily()
        assert s.tavily_monthly_count == 2


class TestConfigLoading:
    def test_default_config(self, tmp_path, monkeypatch):
        # 干净环境（无 ~/.deepseek/config.json / 无环境变量）下，代码默认值不含 API key
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        config = neo_code.load_config()
        assert "BASE_URL" in config
        assert "MODEL" in config
        assert "DEEPSEEK_API_KEY" not in config
        assert "TAVILY_API_KEY" not in config

    def test_env_provides_key(self, tmp_path, monkeypatch):
        # 无内置 key，环境变量提供 DEEPSEEK_API_KEY
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test-123"}):
            config = neo_code.load_config()
            assert config["DEEPSEEK_API_KEY"] == "sk-test-123"

    def test_config_file_provides_key(self, tmp_path, monkeypatch):
        # 无内置 key，配置文件提供 DEEPSEEK_API_KEY
        (tmp_path / ".deepseek").mkdir()
        (tmp_path / ".deepseek" / "config.json").write_text(
            json.dumps({"DEEPSEEK_API_KEY": "sk-file-456"}), encoding="utf-8"
        )
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        config = neo_code.load_config()
        assert config["DEEPSEEK_API_KEY"] == "sk-file-456"

    def test_code_default_wins_over_config_file(self, tmp_path, monkeypatch):
        # 配置文件写入 pro，代码默认 flash → 代码胜出
        (tmp_path / ".deepseek").mkdir()
        (tmp_path / ".deepseek" / "config.json").write_text(
            json.dumps({"MODEL": "deepseek-v4-pro"}), encoding="utf-8"
        )
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        config = neo_code.load_config()
        assert config["MODEL"] == "deepseek-v4-flash"


class TestExitCode:
    def test_values(self):
        assert neo_code.ExitCode.SUCCESS == 0
        assert neo_code.ExitCode.API_ERROR == 1
        assert neo_code.ExitCode.CONFIG_ERROR == 2
        assert neo_code.ExitCode.TOOL_ERROR == 3
        assert neo_code.ExitCode.INTERRUPTED == 130
        assert neo_code.ExitCode.INTERNAL_ERROR == 255
