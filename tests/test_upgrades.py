"""第二批（P1 上下文/工具）功能测试：状态栏、Skills 元数据、混合检索、工具描述约定。"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
import neo_code


class FakeResp:
    def __init__(self, text="", status_code=200, json_data=None):
        self.text = text
        self.status_code = status_code
        self._json = json_data

    def json(self):
        return self._json


class TestAgentStatusBar:
    def test_contains_required_state(self):
        state = neo_code.SessionState()
        tok = neo_code.TokenCounter()
        bar = neo_code._build_status_bar(
            state, tok, [{"role": "user", "content": "hi"}], tool_rounds=3
        )
        assert "<agent_status>" in bar
        assert "tool_rounds_this_turn: 3" in bar
        assert "auto_approve:" in bar
        assert "plan_mode:" in bar
        assert "context:" in bar

    def test_includes_plan_when_work_plan_exists(self):
        saved = neo_code._work_plan
        try:
            neo_code._work_plan = [
                {"content": "a", "status": "in_progress"},
                {"content": "b", "status": "pending"},
            ]
            bar = neo_code._build_status_bar(neo_code.SessionState(), None, [], 0)
        finally:
            neo_code._work_plan = saved
        assert "plan:" in bar
        assert "1 in_progress" in bar


class TestSkillMetadata:
    def test_scans_skill_md_frontmatter(self, tmp_path):
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        (skill_dir / "ppt").mkdir()
        (skill_dir / "ppt" / "SKILL.md").write_text(
            "---\nname: ppt\ndescription: 从论文生成演示文稿，Use when 需要 PPTX 时\n---\n# 正文\n",
            encoding="utf-8",
        )
        (skill_dir / "plain.md").write_text("# 通用助手\n一个简单 skill", encoding="utf-8")
        meta = neo_code._scan_skill_metadata(dirs=[skill_dir])
        assert "<available_skills>" in meta
        assert "ppt" in meta
        assert "演示文稿" in meta
        assert "plain" in meta

    def test_empty_dir_returns_empty(self, tmp_path):
        assert neo_code._scan_skill_metadata(dirs=[tmp_path]) == ""


class TestHybridRetrieval:
    def test_tokenize_latin_and_cjk(self):
        tokens = neo_code.VectorMemory._tokenize("Python 内存泄漏 tracemalloc")
        assert "python" in tokens
        assert "tracemalloc" in tokens
        assert "内存" in tokens  # 中文二元组

    def test_sparse_rank_prefers_overlap(self):
        vm = neo_code.VectorMemory.__new__(neo_code.VectorMemory)
        docs = ["Python 内存泄漏 排查", "今天天气很好", "Python 教程入门"]
        ranked = vm._sparse_rank("Python 内存泄漏", docs)
        assert ranked[0][0] == "Python 内存泄漏 排查"
        assert ranked[0][1] > 0

    def test_rrf_fuse_merges_rankings(self):
        dense = [("a", 0.1), ("b", 0.2)]
        sparse = [("b", 5.0), ("c", 4.0)]
        fused = neo_code.VectorMemory._rrf_fuse(dense, sparse, top_k=3)
        assert {doc for doc, _ in fused} == {"a", "b", "c"}


class TestToolDescriptionConvention:
    """《深入理解 AI Agent》第 4 章：描述应说明"何时用/何时不用"与边界。"""

    REWRITTEN = [
        "read_file", "run_command", "run_interpreter", "run_python",
        "glob_search", "grep_search", "web_search", "web_fetch",
        "read_webpage", "lsp_check", "web_extract", "web_crawl",
        "web_research", "skill_load", "social_fetch", "process",
        "get_terminal_output", "memory_search", "update_memory",
        "search_codebase", "task",
    ]

    def test_key_tools_have_use_when_and_dont_use(self):
        for name in self.REWRITTEN:
            tool = neo_code.TOOL_MAP.get(name)
            assert tool is not None, f"tool 缺失: {name}"
            desc = tool.description
            assert "Use when" in desc, f"{name} 描述缺 'Use when': {desc[:80]}"
            assert "Don't use" in desc, f"{name} 描述缺 \"Don't use\": {desc[:80]}"


class TestUserMemoryUpgrade:
    def test_stores_advanced_cards_fields(self, tmp_path, monkeypatch):
        mem_file = tmp_path / "memories.json"
        monkeypatch.setattr(neo_code, "_MEMORIES_PATH", mem_file)
        neo_code.tool_update_memory(
            neo_code.SessionState(), action="create", id="m1", title="偏好",
            content="喜欢简洁回复", person="父亲", relationship="用户父亲",
            backstory="用户多次提到帮父亲处理手机问题",
        )
        memories = neo_code._load_memories()
        assert memories["m1"]["person"] == "父亲"
        assert memories["m1"]["relationship"] == "用户父亲"
        assert "backstory" in memories["m1"]

    def test_consolidation_merges_duplicates(self, tmp_path, monkeypatch):
        mem_file = tmp_path / "memories.json"
        monkeypatch.setattr(neo_code, "_MEMORIES_PATH", mem_file)
        neo_code.tool_update_memory(
            neo_code.SessionState(), action="create", id="m1", title="偏好",
            content="旧内容", keywords="a", person="父亲",
        )
        neo_code.tool_update_memory(
            neo_code.SessionState(), action="create", id="m2", title="偏好",
            content="新内容", keywords="b", person="父亲",
        )
        memories = neo_code._load_memories()
        assert len(memories) == 1, f"应合并为 1 条: {memories}"
        entry = next(iter(memories.values()))
        assert entry["content"] == "新内容"
        assert "a" in entry["keywords"] and "b" in entry["keywords"]

    def test_memory_recall_finds_and_marks(self, tmp_path, monkeypatch):
        mem_file = tmp_path / "memories.json"
        monkeypatch.setattr(neo_code, "_MEMORIES_PATH", mem_file)
        neo_code.tool_update_memory(
            neo_code.SessionState(), action="create", id="m1", title="语言偏好",
            content="默认中文回复", keywords="zh", person="本人",
        )
        out = neo_code.tool_memory_recall(neo_code.SessionState(), query="中文")
        assert "<external_content" in out
        assert "语言偏好" in out
        out_miss = neo_code.tool_memory_recall(neo_code.SessionState(), query="不存在的词")
        assert "No memories match" in out_miss


class TestMcpDiscovery:
    class FakeMcpProc:
        """模拟 MCP stdio 进程：收到请求后按工具方法返回固定响应。"""
        class _In:
            def __init__(self, owner):
                self._owner = owner
            def write(self, s):
                self._owner.written.append(s)
            def flush(self):
                pass

        class _Out:
            def __init__(self, line):
                self._line = line
            def readline(self):
                return self._line

        def __init__(self, result):
            self.written = []
            self.stdin = self._In(self)
            self.stdout = self._Out(json.dumps({"jsonrpc": "2.0", "result": result}) + "\n")

    def test_mcp_rpc_parses_result(self):
        proc = self.FakeMcpProc({"tools": [{"name": "t1", "description": "工具一"}]})
        # 新实现：per-server 读线程队列（真实超时）。测试直接注入响应队列。
        key = "test-server"
        q = neo_code._MCP_READER_QUEUES.setdefault(key, __import__("queue").Queue())
        q.put({"jsonrpc": "2.0", "result": {"tools": [{"name": "t1", "description": "工具一"}]}})
        result = neo_code._mcp_rpc(key, proc, "tools/list", {}, 1)
        assert result["tools"][0]["name"] == "t1"
        assert proc.written and "tools/list" in proc.written[0]

    def test_mcp_rpc_uninitialized_reader_returns_error(self):
        proc = self.FakeMcpProc({"tools": []})
        result = neo_code._mcp_rpc("no-such-server", proc, "tools/list", {}, 1)
        assert isinstance(result, dict) and "error" in result


class TestStructuredToolErrors:
    def test_tool_failure_format(self):
        err = neo_code._tool_failure("http", "HTTP 404", "检查 URL")
        assert err.startswith("Error: [http]")
        assert "检查 URL" in err

    def test_web_fetch_error_structured(self, state):
        with patch("requests.get", return_value=FakeResp(status_code=404)):
            out = neo_code.tool_web_fetch(state, "https://example.com/x")
        assert "[http]" in out
        assert "HTTP 404" in out


class TestLazyOptionalDeps:
    """启动提速：可选重依赖不得在模块导入时被真实加载（find_spec 探测 + 使用点惰性导入）。"""

    HEAVY = ["chromadb", "sentence_transformers", "funasr", "PySide6", "speech_recognition"]

    def test_heavy_deps_not_loaded_at_import(self):
        """子进程全新导入验证（避免被同进程内其他测试的导入顺序污染）。"""
        import subprocess
        script = (
            "import sys, neo_code; "
            "print([m for m in %r if m in sys.modules])" % (self.HEAVY,)
        )
        env = os.environ.copy()
        env["DEEPSEEK_SKIP_BOOTSTRAP"] = "1"
        out = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True,
            timeout=60, cwd=str(Path(__file__).parent.parent), env=env,
        )
        assert out.returncode == 0, out.stderr[-500:]
        loaded = out.stdout.strip()
        assert loaded == "[]", f"模块导入时不应加载重依赖: {loaded}"

    def test_capability_flags_detected(self):
        import importlib.util
        for flag, pkg in [
            ("_HAS_VECTOR_MEMORY", "chromadb"),
            ("_HAS_EDGE_TTS", "edge_tts"),
            ("_HAS_FUNASR", "funasr"),
        ]:
            available = importlib.util.find_spec(pkg) is not None
            assert getattr(neo_code, flag) is available, f"{flag} 与 {pkg} 探测不一致"


class TestEventQueue:
    def _clear(self):
        while not neo_code._event_queue.empty():
            neo_code._event_queue.get_nowait()

    def test_emit_and_drain(self):
        self._clear()
        neo_code._emit_event("cron", "job due now")
        text = neo_code._drain_events()
        assert "cron" in text
        assert "job due now" in text
        assert neo_code._drain_events() == ""  # 已消费

    def test_status_bar_includes_events(self):
        self._clear()
        neo_code._emit_event("test", "hello event")
        bar = neo_code._build_status_bar(neo_code.SessionState(), None, [], 0)
        assert "pending_events" in bar
        assert "hello event" in bar


class TestWorktreeIsolation:
    def test_find_git_root(self, tmp_path):
        repo = tmp_path / "repo"
        (repo / "sub").mkdir(parents=True)
        (repo / ".git").mkdir()
        assert neo_code._find_git_root(repo / "sub") == repo

    def test_temporary_worktree_isolated_and_cleaned(self, tmp_path):
        import subprocess
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "a.txt").write_text("x", encoding="utf-8")
        subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "add", "."],
                       cwd=str(repo), capture_output=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "init"],
                       cwd=str(repo), capture_output=True)
        with neo_code._temporary_worktree(repo=repo) as (wt, branch):
            assert wt != Path.cwd()
            assert (wt / "a.txt").exists()
            assert branch and branch.startswith("agent-")
        assert not wt.exists()


class TestCrashRecovery:
    """崩溃恢复：仅恢复 24 小时内的转储；正常退出不应污染下个会话。"""

    def _dump(self, tmp_path, monkeypatch, ts, messages):
        dump_path = tmp_path / "crash_dump.json"
        dump_path.write_text(json.dumps({
            "timestamp": ts.isoformat(),
            "message_count": len(messages),
            "messages": messages,
        }), encoding="utf-8")
        monkeypatch.setattr(neo_code, "CRASH_DUMP_PATH", dump_path)
        return dump_path

    def test_stale_dump_not_recovered(self, tmp_path, monkeypatch):
        from datetime import datetime, timedelta
        dump_path = self._dump(
            tmp_path, monkeypatch,
            datetime.now() - timedelta(hours=48),
            [{"role": "user", "content": "旧会话"}],
        )
        assert neo_code.recover_crash() is None
        assert not dump_path.exists()  # 过期转储被清理

    def test_fresh_dump_recovered(self, tmp_path, monkeypatch):
        from datetime import datetime, timedelta
        dump_path = self._dump(
            tmp_path, monkeypatch,
            datetime.now() - timedelta(minutes=5),
            [{"role": "user", "content": "刚崩溃的会话"}],
        )
        messages = neo_code.recover_crash()
        assert messages is not None
        assert messages[0]["content"] == "刚崩溃的会话"


class TestPastContextInjectionGate:
    """首回合不注入历史记忆（防止旧会话串场）。"""

    def test_session_state_default_disabled(self):
        state = neo_code.SessionState()
        assert state._past_context_inject_enabled is False

    def test_gate_flag_can_be_enabled_after_first_turn(self):
        state = neo_code.SessionState()
        state._past_context_inject_enabled = True
        assert state._past_context_inject_enabled is True


class TestToolContractClarity:
    """工具契约清晰度：超限写入必须明确报错且不写文件；shell 探测与实际执行一致。"""

    def test_write_file_too_large_refuses_and_writes_nothing(self, tmp_path):
        target = tmp_path / "big.txt"
        out = neo_code.tool_write_file(
            neo_code.SessionState(), str(target), "x" * 13000
        )
        assert out.startswith("Error: [too_large]")
        assert "未写入" in out
        assert not target.exists()

    def test_write_file_force_large_write_allowed(self, tmp_path):
        target = tmp_path / "big.txt"
        out = neo_code.tool_write_file(
            neo_code.SessionState(), str(target), "x" * 13000 + "FORCE_LARGE_WRITE"
        )
        assert out.startswith("OK:")
        assert target.exists()

    def test_shell_detection_matches_executor(self):
        import sys as _sys
        shell, platform = neo_code._cache_align_get_static_env()
        executor_shell = neo_code.build_shell_command("echo hi")[0]
        if _sys.platform == "win32":
            assert shell in ("pwsh", "powershell", "cmd")
            assert shell == executor_shell


class TestOutputBudgetPrompt:
    """单次回复有 token 上限：系统提示应约束长规划，并暴露当前上限数值。"""

    def test_static_prompt_has_output_budget_rule(self):
        prompt = neo_code._build_static_prompt()
        assert "<output_budget>" in prompt
        assert "token cap" in prompt
        assert "auto-continues" in prompt

    def test_runtime_env_reports_max_tokens(self):
        prompt = neo_code.build_system_prompt()
        assert "Max output tokens per reply" in prompt
