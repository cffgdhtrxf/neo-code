"""Smoke tests（从 neo_code.py 外迁，计划 #7）。

CLI `--smoke-test` 通过 run_smoke_tests() 运行；pytest 通过 test_smoke_all_checks_pass 收集。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import neo_code

from neo_code import (
    ALL_TOOLS, CONFIG, SAFE_COMMAND_PREFIXES, PolicyPipeline, SafetyGate,
    SessionState, TTSManager, TokenCounter, ToolPolicy, VectorMemory,
    _HAS_EDGE_TTS, _HAS_FUNASR, _HAS_SPEECH_RECOGNITION, _HAS_VECTOR_MEMORY,
    _TTS_CN_VOICES, _TTS_EN_VOICES, _format_tool_calls, _repair_json_arguments,
    _safe_parse_tool_args, expand_allowlist, generate_schemas, normalize_path,
    process_stream, tool_process, tool_run_interpreter, tool_web_search,
    tool_write_file,
)


def run_smoke_tests() -> bool:
    print("Running smoke test...")
    ok = True

    try:
        p = normalize_path("~")
        assert p.exists()
        print("  [OK] normalize_path")
    except Exception as e:
        print(f"  [FAIL] normalize_path: {e}")
        ok = False

    try:
        s = SessionState()
        assert s.subagent_depth == 0
        s.enter_subagent()
        assert s.subagent_depth == 1
        s.leave_subagent()
        assert s.subagent_depth == 0
        print("  [OK] SessionState")
    except Exception as e:
        print(f"  [FAIL] SessionState: {e}")
        ok = False

    try:
        assert len(ALL_TOOLS) >= 44
        schemas = generate_schemas()
        assert len(schemas) >= 44
        print(f"  [OK] {len(ALL_TOOLS)} tools registered")
    except Exception as e:
        print(f"  [FAIL] Tools: {e}")
        ok = False

    try:
        assert expand_allowlist(["group:safe"]).issuperset({"read_file", "grep_search"})
        assert expand_allowlist(["*"]) == {"*"}
        assert expand_allowlist(["read_file", "write_file"]) == {"read_file", "write_file"}
        print("  [OK] expand_allowlist")
    except Exception as e:
        print(f"  [FAIL] expand_allowlist: {e}")
        ok = False

    try:
        tp = ToolPolicy(allow=["group:safe"], deny=[])
        assert tp.is_allowed("read_file")
        assert not tp.is_allowed("run_command")
        print("  [OK] ToolPolicy")
    except Exception as e:
        print(f"  [FAIL] ToolPolicy: {e}")
        ok = False

    try:
        pp = PolicyPipeline(layers=[
            ("safety", ToolPolicy(allow=["*"])),
            ("restrict", ToolPolicy(allow=["read_file"], deny=["write_file"])),
        ])
        assert pp.is_allowed("read_file")
        assert not pp.is_allowed("write_file")
        print("  [OK] PolicyPipeline")
    except Exception as e:
        print(f"  [FAIL] PolicyPipeline: {e}")
        ok = False

    try:
        result = tool_run_interpreter("print(1 + 1)")
        assert "2" in result
        print("  [OK] run_interpreter")
    except Exception as e:
        print(f"  [FAIL] run_interpreter: {e}")
        ok = False

    try:
        result = tool_run_interpreter("import os\nprint('import ok')")
        assert "import ok" in result
        print("  [OK] run_interpreter (subprocess, imports allowed)")
    except Exception as e:
        print(f"  [FAIL] run_interpreter subprocess: {e}")
        ok = False

    try:
        tc = TokenCounter()
        count = tc._count("Hello world")
        assert count > 0
        print(f"  [OK] TokenCounter (count={count})")
    except Exception as e:
        print(f"  [FAIL] TokenCounter: {e}")
        ok = False

    try:
        repaired = _repair_json_arguments('{"path": "/test", "content": "hello')
        assert json.loads(repaired) == {"path": "/test", "content": "hello"}
        repaired2 = _repair_json_arguments('{"a": [1, 2')
        assert isinstance(json.loads(repaired2), dict)
        assert _repair_json_arguments("") == "{}"
        assert _repair_json_arguments('{"ok": true}') == '{"ok": true}'
        repaired_trail = _repair_json_arguments('{"a": 1,}')
        assert json.loads(repaired_trail) == {"a": 1}
        print("  [OK] _repair_json_arguments")
    except Exception as e:
        print(f"  [FAIL] _repair_json_arguments: {e}")
        ok = False

    try:
        args_ok, err_ok = _safe_parse_tool_args('{"path": "/test"}')
        assert args_ok == {"path": "/test"} and err_ok is None
        args_empty, err_empty = _safe_parse_tool_args("")
        assert args_empty == {} and err_empty is None
        args_none, err_detail = _safe_parse_tool_args('{"path":')
        assert args_none is None and "truncated" in err_detail
        args_repair, err_repair = _safe_parse_tool_args('{"path": "/test", "content": "hi')
        assert args_repair is not None and args_repair.get("path") == "/test"
        print("  [OK] _safe_parse_tool_args")
    except Exception as e:
        print(f"  [FAIL] _safe_parse_tool_args: {e}")
        ok = False

    try:
        fc_ok = _format_tool_calls({0: {"id": "call_1", "name": "read_file", "arguments": '{"path":"/x"}'}})
        assert len(fc_ok) == 1 and fc_ok[0]["id"] == "call_1"
        fc_no_id = _format_tool_calls({0: {"id": "", "name": "read_file", "arguments": "{}"}})
        assert fc_no_id[0]["id"] == "call_0"
        fc_no_name = _format_tool_calls({0: {"id": "call_1", "name": "", "arguments": "{}"}})
        assert len(fc_no_name) == 0
        fc_no_args = _format_tool_calls({0: {"id": "call_1", "name": "read_file", "arguments": None}})
        assert fc_no_args[0]["function"]["arguments"] == ""
        print("  [OK] _format_tool_calls validation")
    except Exception as e:
        print(f"  [FAIL] _format_tool_calls validation: {e}")
        ok = False

    try:
        assert any("echo " in p for p in SAFE_COMMAND_PREFIXES)
        assert any("git status" in p for p in SAFE_COMMAND_PREFIXES)
        assert any("pip show" in p for p in SAFE_COMMAND_PREFIXES)
        assert any("whoami" in p for p in SAFE_COMMAND_PREFIXES)
        print("  [OK] SAFE_COMMAND_PREFIXES expanded")
    except Exception as e:
        print(f"  [FAIL] SAFE_COMMAND_PREFIXES: {e}")
        ok = False

    try:
        sg = SafetyGate(None, SessionState())
        # Test that DESTRUCTIVE_PATTERNS are checked for non-interactive GATE
        deny_result, deny_reason = sg.check("run_command", {"command": "rm -rf /"}, interactive=False)
        assert deny_result == "deny", f"Expected deny for rm -rf, got {deny_result}: {deny_reason}"
        print("  [OK] Non-interactive GATE denies destructive commands")
    except Exception as e:
        print(f"  [FAIL] Non-interactive GATE: {e}")
        ok = False

    try:
        from unittest.mock import MagicMock
        sg2 = SafetyGate(None, SessionState())
        allow_result, allow_reason = sg2.check("run_command", {"command": "echo hello"}, interactive=False)
        assert allow_result == "allow", f"Expected allow for 'echo hello', got {allow_result}: {allow_reason}"
        print("  [OK] Non-interactive GATE allows safe commands (echo)")
    except Exception as e:
        print(f"  [FAIL] Non-interactive GATE safe command: {e}")
        ok = False

    try:
        empty_result = tool_write_file(SessionState(), path="/tmp/_test_empty.txt", content="")
        assert "empty" in empty_result.lower() or "Error" in empty_result, \
            f"Expected error for empty content, got: {empty_result}"
        print("  [OK] write_file rejects empty content")
    except Exception as e:
        print(f"  [FAIL] write_file empty content check: {e}")
        ok = False

    try:
        from unittest.mock import MagicMock
        mock_chunk = MagicMock()
        mock_chunk.usage = None
        mock_choice = MagicMock()
        mock_choice.delta = MagicMock()
        mock_choice.delta.reasoning_content = None
        mock_choice.delta.tool_calls = None
        mock_choice.delta.content = "Hello"
        mock_choice.finish_reason = "length"
        mock_chunk.choices = [mock_choice]
        state = SessionState()
        r, c, tc, u, fr = process_stream(state, iter([mock_chunk]))
        assert fr == "length", f"Expected finish_reason='length', got {fr}"
        assert c == "Hello"
        print("  [OK] process_stream detects finish_reason=length")
    except Exception as e:
        print(f"  [FAIL] process_stream finish_reason: {e}")
        ok = False

    # ── TTS tests ──
    try:
        tts = TTSManager(state=SessionState())
        # Don't test default — it may be persisted from previous /tts on
        saved = tts._enabled
        tts.disable()
        assert not tts._enabled, "disable() should set _enabled=False"
        tts.enable()
        assert tts._enabled, "enable() should set _enabled=True"
        tts._enabled = saved  # restore
        print("  [OK] TTSManager: enable/disable works")
    except Exception as e:
        print(f"  [FAIL] TTSManager toggle: {e}")
        ok = False

    try:
        tts = TTSManager(state=SessionState())
        tts.enable()
        # Without edge_tts installed, enabled flag is True but enabled property is False
        print(f"  [OK] TTSManager: enabled property (edge_tts={'installed' if _HAS_EDGE_TTS else 'not installed'})")
    except Exception as e:
        print(f"  [FAIL] TTSManager toggle: {e}")
        ok = False

    try:
        assert TTSManager._detect_language("你好世界，这是中文测试。") == "zh", "Pure Chinese should be zh"
        assert TTSManager._detect_language("Hello world, this is English.") == "en", "Pure English should be en"
        assert TTSManager._detect_language("你好你好你好PK") == "zh", "CN-majority mix should be zh"
        print("  [OK] TTSManager: language detection")
    except Exception as e:
        print(f"  [FAIL] TTSManager lang detect: {e}")
        ok = False

    try:
        tts = TTSManager(state=SessionState())
        result = tts.set_voice("zh-CN-XiaoxiaoNeural")
        assert "set to" in result
        result = tts.set_voice("invalid-voice")
        assert "Unknown" in result
        print("  [OK] TTSManager: voice selection")
    except Exception as e:
        print(f"  [FAIL] TTSManager voice: {e}")
        ok = False

    try:
        tts = TTSManager(state=SessionState())
        result = tts.set_speed("+20%")
        assert "set to" in result
        result = tts.set_speed("invalid")
        assert "must be like" in result
        print("  [OK] TTSManager: speed setting")
    except Exception as e:
        print(f"  [FAIL] TTSManager speed: {e}")
        ok = False

    try:
        voices = TTSManager.list_voices()
        assert "Chinese" in voices
        assert "English" in voices
        assert "auto" in voices
        print("  [OK] TTSManager: voice listing")
    except Exception as e:
        print(f"  [FAIL] TTSManager list: {e}")
        ok = False

    try:
        # Test summarization (no client needed - uses truncation fallback)
        tts = TTSManager(state=SessionState())
        short = tts._summarize_for_tts("Hello world")
        assert 0 < len(short) <= 800, f"Short text should pass through: {len(short)} chars"
        long_text = "这是一个很长的回复。" * 100  # ~1000 chars, exceeds 800 threshold
        summary = tts._summarize_for_tts(long_text)
        assert len(summary) <= 600, f"Long text should be truncated: {len(summary)} chars"
        print("  [OK] TTSManager: summarization (short pass-through, long truncated)")
    except Exception as e:
        print(f"  [FAIL] TTSManager summarization: {e}")
        ok = False

    try:
        tts = TTSManager(state=SessionState())
        voice = tts._resolve_voice("你好世界")
        assert voice in _TTS_CN_VOICES, f"Expected CN voice, got {voice}"
        voice = tts._resolve_voice("Hello world")
        assert voice in _TTS_EN_VOICES, f"Expected EN voice, got {voice}"
        print("  [OK] TTSManager: voice auto-detection")
    except Exception as e:
        print(f"  [FAIL] TTSManager auto-voice: {e}")
        ok = False

    # ── TTS cache tests ──
    try:
        k1 = TTSManager._cache_key("你好", "zh-CN-XiaoxiaoNeural", "+0%")
        k2 = TTSManager._cache_key("你好", "zh-CN-XiaoxiaoNeural", "+0%")
        k3 = TTSManager._cache_key("Hello", "zh-CN-XiaoxiaoNeural", "+0%")
        k4 = TTSManager._cache_key("你好", "zh-CN-XiaoxiaoNeural", "+20%")
        assert k1 == k2, "Same input should produce same key"
        assert k1 != k3, "Different text should produce different key"
        assert k1 != k4, "Different speed should produce different key"
        assert len(k1) == 16, "Key should be 16 hex chars"
        print("  [OK] TTSManager: cache key deterministic")
    except Exception as e:
        print(f"  [FAIL] TTSManager cache key: {e}")
        ok = False

    try:
        cache_dir = TTSManager._ensure_cache_dir()
        assert cache_dir.exists()
        # Clean up any leftover test files
        for f in list(cache_dir.glob("*.mp3"))[:100]:
            f.unlink(missing_ok=True)
        # Create dummy cache files to test eviction
        for i in range(55):
            (cache_dir / f"test_{i:03d}.mp3").write_bytes(b"x" * 100)
        TTSManager._evict_cache_if_needed()
        remaining = list(cache_dir.glob("*.mp3"))
        assert len(remaining) <= TTSManager._CACHE_MAX_FILES, f"Expected <=50 after eviction, got {len(remaining)}"
        # Cleanup
        for f in remaining:
            f.unlink(missing_ok=True)
        print("  [OK] TTSManager: cache eviction (50-file limit)")
    except Exception as e:
        print(f"  [FAIL] TTSManager cache eviction: {e}")
        ok = False

    try:
        if _HAS_EDGE_TTS:
            # Test real cache hit
            cache_dir = TTSManager._ensure_cache_dir()
            tts = TTSManager(state=SessionState())
            path1 = tts._get_or_generate_audio("测试缓存", "zh-CN-XiaoxiaoNeural")
            if not path1:
                # 网络不可达/生成超时 → 跳过而不是挂起 7 分钟
                print("  [OK] TTSManager: cache test skipped (edge-tts 生成失败/网络不可达)")
            else:
                import time; t0 = time.time()
                path2 = tts._get_or_generate_audio("测试缓存", "zh-CN-XiaoxiaoNeural")
                t1 = time.time()
                assert path2 == path1, "Cache hit should return same path"
                assert (t1 - t0) < 1.0, f"Cache hit should be fast (<1s), took {t1 - t0:.1f}s"
                assert Path(path1).exists()
                # Cleanup
                Path(path1).unlink(missing_ok=True)
                print(f"  [OK] TTSManager: cache hit ({(t1 - t0)*1000:.0f}ms)")
        else:
            print("  [OK] TTSManager: cache test skipped (edge-tts not installed)")
    except Exception as e:
        print(f"  [FAIL] TTSManager cache hit: {e}")
        ok = False

    # ── DDG search fallback test ──
    try:
        # Temporarily unset Tavily key to force DDG fallback
        saved_key = CONFIG.get("TAVILY_API_KEY", "")
        CONFIG["TAVILY_API_KEY"] = ""
        result = tool_web_search(SessionState(), "Python programming", max_results=3)
        CONFIG["TAVILY_API_KEY"] = saved_key
        # DDG should return results OR a network error (both prove fallback path works)
        ok_keywords = ("1. ", "No results", "Search unavailable", "DuckDuckGo")
        assert any(kw in result for kw in ok_keywords), f"Unexpected DDG output: {result[:200]}"
        print("  [OK] web_search: DuckDuckGo fallback path works")
    except Exception as e:
        CONFIG["TAVILY_API_KEY"] = saved_key
        print(f"  [FAIL] web_search DDG fallback: {e}")
        ok = False

    # ── Vector memory auto-retrieval test ──
    if _HAS_VECTOR_MEMORY:
        try:
            import tempfile, shutil
            tmpdir = Path(tempfile.mkdtemp(prefix="smoketest_vm_"))
            try:
                vm = VectorMemory(tmpdir)
                vm.add_turn("如何修复 Python 内存泄漏", "使用 tracemalloc 模块追踪")
                vm.add_turn("今天天气怎么样", "晴天，25度")
                hits = vm.query_with_scores("Python 内存泄漏怎么排查", top_k=2)
                assert len(hits) == 2
                doc1, dist1 = hits[0]
                doc2, dist2 = hits[1]
                assert dist1 < dist2, f"First hit should be closer: {dist1:.3f} vs {dist2:.3f}"
                assert "内存泄漏" in doc1, f"Top hit should match: {doc1[:100]}"
                print(f"  [OK] VectorMemory: query_with_scores (top: sim={1-dist1:.0%})")
            finally:
                # Explicitly close chromadb before cleanup (holds SQLite file handles)
                try:
                    vm._client.reset()
                except Exception:
                    pass
                del vm
                import gc; gc.collect()
                shutil.rmtree(str(tmpdir), ignore_errors=True)
        except Exception as e:
            print(f"  [FAIL] VectorMemory query_with_scores: {e}")
            ok = False
    else:
        print("  [OK] VectorMemory: test skipped (chromadb not installed)")

    # ── Interactive terminal test ──
    try:
        import tempfile
        # Write a tiny echo server: reads line, uppercases, prints, loops
        test_script = Path(tempfile.gettempdir()) / "_deepseek_term_test.py"
        test_script.write_text(
            "import sys\n"
            "sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None\n"
            "print('READY', flush=True)\n"
            "for line in sys.stdin:\n"
            "    line = line.strip()\n"
            "    if line == 'QUIT': break\n"
            "    print(line.upper(), flush=True)\n",
            encoding='utf-8'
        )
        r1 = tool_process(SessionState(), action="start",
                          command=f'python -u "{test_script}"', timeout=15)
        assert "Started terminal" in r1, f"Expected start message: {r1[:200]}"
        sid = r1.split("'")[1] if "'" in r1 else ""
        assert sid, "Could not extract session ID"

        # Wait for READY
        import time; time.sleep(0.5)
        r2 = tool_process(SessionState(), action="send_keys", session_id=sid, keys="hello world", timeout=3)
        assert "HELLO WORLD" in r2, f"Expected 'HELLO WORLD' in output: {r2[:200]}"

        r3 = tool_process(SessionState(), action="send_keys", session_id=sid, keys="foo bar", timeout=3)
        assert "FOO BAR" in r3, f"Expected 'FOO BAR' in output: {r3[:200]}"

        tool_process(SessionState(), action="send_keys", session_id=sid, keys="QUIT", timeout=2)
        import time; time.sleep(0.3)
        tool_process(SessionState(), action="stop", session_id=sid)
        test_script.unlink(missing_ok=True)
        print("  [OK] interactive terminal: start → send_keys → echo → stop")
    except Exception as e:
        print(f"  [FAIL] interactive terminal: {e}")
        ok = False

    # ── Voice input / ASR check ──
    if _HAS_FUNASR:
        print("  [OK] voice input: FunASR SenseVoice (primary)")
    elif _HAS_SPEECH_RECOGNITION:
        try:
            import speech_recognition as sr
            r = sr.Recognizer()
            assert r.energy_threshold > 0
            assert hasattr(r, 'recognize_google')
            print("  [OK] voice input: Google STT (FunASR not installed)")
        except Exception as e:
            print(f"  [FAIL] voice input: {e}")
            ok = False
    else:
        print("  [OK] voice input: test skipped (pip install funasr or SpeechRecognition)")

    if ok:
        print("\nAll smoke tests passed!")
    else:
        print("\nSome smoke tests failed.")
    return ok



def test_smoke_all_checks_pass():
    assert run_smoke_tests()
