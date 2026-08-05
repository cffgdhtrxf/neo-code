import sys
import os
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))
import neo_code


class TestReadFile:
    def test_read_existing(self, state, sample_file):
        result = neo_code.tool_read_file(state, str(sample_file))
        assert "Hello World" in result
        assert "1:" in result

    def test_read_nonexistent(self, state, tmp_path):
        result = neo_code.tool_read_file(state, str(tmp_path / "nope.txt"))
        assert "Error" in result

    def test_read_with_offset(self, state, sample_file):
        result = neo_code.tool_read_file(state, str(sample_file), offset=1)
        assert "2:" in result

    def test_read_with_limit(self, state, sample_file):
        result = neo_code.tool_read_file(state, str(sample_file), limit=1)
        assert "1:" in result
        assert "more lines" in result


class TestWriteFile:
    def test_write_new_file(self, state, tmp_path):
        f = tmp_path / "new.txt"
        result = neo_code.tool_write_file(state, str(f), "hello")
        assert "OK" in result
        assert f.read_text(encoding="utf-8") == "hello"

    def test_write_creates_parents(self, state, tmp_path):
        f = tmp_path / "sub" / "dir" / "file.txt"
        result = neo_code.tool_write_file(state, str(f), "content")
        assert "OK" in result
        assert f.exists()

    def test_write_cache_invalidated(self, state, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("old", encoding="utf-8")
        neo_code.cached_read(state, f)
        neo_code.tool_write_file(state, str(f), "new")
        assert str(f.resolve()) not in state.file_cache


class TestRunCommand:
    def test_simple_command(self, state):
        result = neo_code.tool_run_command(state, "echo hello", timeout=10)
        assert "hello" in result
        assert "Exit code: 0" in result

    def test_command_timeout(self, state):
        if sys.platform == "win32":
            result = neo_code.tool_run_command(state, "ping -n 30 127.0.0.1", timeout=2)
        else:
            result = neo_code.tool_run_command(state, "sleep 30", timeout=2)
        assert "Timeout" in result or "timeout" in result.lower()

    def test_shell_fallback(self, state):
        result = neo_code.tool_run_command(state, "echo test", timeout=10)
        assert "test" in result

    def test_cache_invalidation(self, state, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("original", encoding="utf-8")
        neo_code.cached_read(state, f)
        if sys.platform == "win32":
            neo_code.tool_run_command(state, f'echo modified > "{f}"', timeout=10)
        else:
            neo_code.tool_run_command(state, f'echo modified > "{f}"', timeout=10)
        assert str(f.resolve()) not in state.file_cache


class TestRunInterpreter:
    def test_basic_print(self):
        result = neo_code.tool_run_interpreter("print(1 + 1)")
        assert "2" in result

    def test_import_allowed(self):
        result = neo_code.tool_run_interpreter("import os\nprint('import ok')")
        assert "import ok" in result

    def test_stdlib_imports(self):
        result = neo_code.tool_run_interpreter(
            "import json, math, re\n"
            "print(json.dumps({'a': 1}), math.sqrt(16), bool(re.search(r'\\d+', 'abc123')))"
        )
        assert '"a"' in result
        assert "4.0" in result
        assert "True" in result

    def test_syntax_error(self):
        result = neo_code.tool_run_interpreter("def (:")
        assert "SyntaxError" in result

    def test_runtime_error_reported(self):
        result = neo_code.tool_run_interpreter("1 / 0")
        assert "ZeroDivisionError" in result

    def test_function_definition(self):
        code = "def fib(n):\n    a, b = 0, 1\n    for _ in range(n):\n        a, b = b, a + b\n    return a\nprint(fib(10))"
        result = neo_code.tool_run_interpreter(code)
        assert "55" in result

    def test_list_comprehension(self):
        result = neo_code.tool_run_interpreter("print([x*2 for x in range(5)])")
        assert "[0, 2, 4, 6, 8]" in result

    def test_try_except(self):
        code = "try:\n    x = 1/0\nexcept ZeroDivisionError:\n    print('caught')"
        result = neo_code.tool_run_interpreter(code)
        assert "caught" in result

    def test_output_truncated(self):
        result = neo_code.tool_run_interpreter("print('x' * 10000)")
        assert "omitted" in result

    def test_timeout(self):
        result = neo_code.tool_run_interpreter("x = 0\nwhile True:\n    x += 1", timeout=2)
        assert "Timeout" in result


class TestListFiles:
    def test_list_directory(self, state, tmp_path):
        (tmp_path / "file1.txt").write_text("a", encoding="utf-8")
        (tmp_path / "file2.txt").write_text("b", encoding="utf-8")
        (tmp_path / "subdir").mkdir()
        result = neo_code.tool_list_files(state, str(tmp_path))
        assert "file1.txt" in result
        assert "file2.txt" in result
        assert "DIR" in result

    def test_not_a_directory(self, state, sample_file):
        result = neo_code.tool_list_files(state, str(sample_file))
        assert "Error" in result


class TestGlobSearch:
    def test_find_files(self, state, tmp_path):
        (tmp_path / "a.py").write_text("", encoding="utf-8")
        (tmp_path / "b.txt").write_text("", encoding="utf-8")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "c.py").write_text("", encoding="utf-8")
        result = neo_code.tool_glob_search(state, str(tmp_path), "*.py")
        assert "a.py" in result
        assert "c.py" in result
        assert "b.txt" not in result

    def test_no_matches(self, state, tmp_path):
        result = neo_code.tool_glob_search(state, str(tmp_path), "*.xyz")
        assert "No files" in result


class TestGrepSearch:
    def test_find_content(self, state, tmp_path):
        (tmp_path / "test.py").write_text("def hello():\n    print('world')\n", encoding="utf-8")
        result = neo_code.tool_grep_search(state, str(tmp_path), "hello", "*.py")
        assert "hello" in result

    def test_no_matches(self, state, tmp_path):
        (tmp_path / "test.py").write_text("print('hi')\n", encoding="utf-8")
        result = neo_code.tool_grep_search(state, str(tmp_path), "xyz_not_found")
        assert "No matches" in result


class TestDocumentValidation:
    def test_valid_json(self, state, sample_json):
        result = neo_code.tool_document_validation(state, str(sample_json))
        assert "OK" in result

    def test_invalid_json(self, state, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("{invalid json}", encoding="utf-8")
        result = neo_code.tool_document_validation(state, str(f))
        assert "Error" in result

    def test_valid_markdown(self, state, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("# Title\n\nSome text\n", encoding="utf-8")
        result = neo_code.tool_document_validation(state, str(f))
        assert "OK" in result

    def test_unclosed_code_block(self, state, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("# Title\n```python\nprint('hi')\n", encoding="utf-8")
        result = neo_code.tool_document_validation(state, str(f))
        assert "unclosed" in result.lower()


class TestToolRegistry:
    def test_registered_tool_count(self):
        assert len(neo_code.ALL_TOOLS) >= 44

    def test_tool_map_complete(self):
        expected = [
            "read_file", "write_file", "edit_file", "apply_patch",
            "run_command", "run_interpreter", "list_files", "glob_search",
            "grep_search", "web_search", "web_fetch", "read_webpage",
            "task", "question", "todowrite", "notebook_read",
            "document_validation", "lsp_check",
        ]
        for name in expected:
            assert name in neo_code.TOOL_MAP, f"Missing tool: {name}"

    def test_schemas_generated(self):
        schemas = neo_code.generate_schemas()
        assert len(schemas) == len(neo_code.ALL_TOOLS)
        for s in schemas:
            assert s["type"] == "function"
            assert "name" in s["function"]
            assert "parameters" in s["function"]


class TestExecuteToolSafeContract:
    """工具分发边界契约：无论成功/失败/异常，模型拿到的永远是字符串。"""

    def test_unknown_tool_returns_string(self, state):
        result = neo_code._execute_tool_safe(state, "no_such_tool", {}, None)
        assert isinstance(result, str)
        assert "unknown tool" in result

    def test_raising_handler_returns_string(self, state):
        original = neo_code.TOOL_MAP["grep_search"].handler

        def boom(state=None, **kwargs):
            raise RuntimeError("kaboom")

        try:
            neo_code.TOOL_MAP["grep_search"].handler = boom
            result = neo_code._execute_tool_safe(state, "grep_search", {}, None)
        finally:
            neo_code.TOOL_MAP["grep_search"].handler = original
        assert isinstance(result, str)
        assert "kaboom" in result

    def test_normal_tool_returns_string(self, state, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("hello", encoding="utf-8")
        result = neo_code._execute_tool_safe(
            state, "read_file", {"path": str(f)}, None
        )
        assert isinstance(result, str)
        assert "hello" in result


class TestFileLockThreadSafety:
    def test_concurrent_get_file_lock_returns_same_instance(self, tmp_path):
        import threading
        f = tmp_path / "a.txt"
        results = []

        def grab():
            results.append(neo_code._get_file_lock(f))

        threads = [threading.Thread(target=grab) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(results) == 8
        assert all(r is results[0] for r in results)
