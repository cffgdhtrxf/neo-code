"""第三批（P1 进化/协作）测试：hermes 评价先行闭环、乐观锁、交叉验证。"""

import json
import sys
import os
import time
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))
import neo_code


class TestTrajectoryAndVerification:
    def test_save_trajectory_append_only(self, tmp_path, monkeypatch):
        monkeypatch.setattr(neo_code, "_hermes_trajectories_dir", tmp_path)
        msgs = [{"role": "user", "content": "hi"}]
        ref1 = neo_code._save_trajectory(msgs, "t1")
        ref2 = neo_code._save_trajectory(msgs, "t2")
        assert ref1 != ref2
        fname = ref1.split(":")[0]
        lines = (tmp_path / fname).read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2

    def test_verify_detects_tool_errors(self):
        msgs = [
            {"role": "user", "content": "do it"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "function": {"name": "run_command", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "Error: command failed"},
        ]
        diags = neo_code._verify_trajectory(msgs)
        by_dim = {d["dimension"]: d["verdict"] for d in diags}
        assert by_dim["result"] == "fail"
        assert by_dim["process"] == "pass"

    def test_verify_detects_repeated_tool(self):
        msgs = []
        for i in range(3):
            msgs.append({"role": "assistant", "content": "", "tool_calls": [{"id": f"c{i}", "function": {"name": "read_file", "arguments": "{}"}}]})
            msgs.append({"role": "tool", "tool_call_id": f"c{i}", "content": "data"})
        diags = neo_code._verify_trajectory(msgs)
        by_dim = {d["dimension"]: d["verdict"] for d in diags}
        assert by_dim["process"] == "fail"
        assert "read_file" in diags[1]["evidence"]

    def test_verify_promise_action_inconsistency(self):
        msgs = [
            {"role": "assistant", "content": "我已经完成了", "tool_calls": [{"id": "c1", "function": {"name": "write_file", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "Error: denied"},
            {"role": "assistant", "content": "已完成所有任务"},
        ]
        diags = neo_code._verify_trajectory(msgs)
        by_dim = {d["dimension"]: d["verdict"] for d in diags}
        assert by_dim["promise_action"] == "fail"


class TestHermesCollectApply:
    def _client_mock(self, items):
        client = MagicMock()
        client.flash_chat.return_value = json.dumps({"rubric": {"task_result": "pass"}, "items": items})
        return client

    def test_collect_saves_trajectory_and_marks_verified(self, tmp_path, monkeypatch):
        monkeypatch.setattr(neo_code, "_hermes_trajectories_dir", tmp_path)
        monkeypatch.setattr(neo_code, "_hermes_pending", [])
        monkeypatch.setattr(neo_code, "_hermes_id_counter", 0)
        history = tmp_path / "history.json"
        history.write_text(json.dumps({"messages": [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]}), encoding="utf-8")
        monkeypatch.setattr(neo_code, "HISTORY_FILE", history)
        saved_client = neo_code._global_client
        try:
            neo_code._global_client = self._client_mock([{
                "category": "preference", "title": "喜欢中文", "applies_when": "回复时",
                "strategy": "默认中文回复", "target_file": "DEEPSEEK.md",
            }])
            out = neo_code.tool_hermes_collect(neo_code.SessionState(), max_turns=5)
        finally:
            neo_code._global_client = saved_client
        assert "h1" in out
        assert "✓已验证" in out
        assert neo_code._hermes_pending, "应生成候选条目"
        assert neo_code._hermes_pending[0]["verified"] is True
        assert neo_code._hermes_pending[0]["source_trajectory"]

    def test_apply_backup_and_rollback(self, tmp_path, monkeypatch):
        monkeypatch.setattr(neo_code, "_hermes_backups_dir", tmp_path / "backups")
        target = tmp_path / "DEEPSEEK.md"
        target.write_text("original content\n", encoding="utf-8")
        entry = {
            "id": "h9", "category": "pitfall", "title": "某坑", "detail": "d",
            "applies_when": "场景", "strategy": "做法", "target_file": str(target),
            "verified": True, "source_trajectory": "20260802.jsonl:t1",
        }
        monkeypatch.setattr(neo_code, "_hermes_pending", [dict(entry)])
        monkeypatch.setattr(neo_code, "_hermes_applied", [])
        out = neo_code.tool_hermes_apply(neo_code.SessionState(), action="apply", entry_id="h9")
        assert "Applied" in out
        assert "某坑" in target.read_text(encoding="utf-8")
        assert neo_code._hermes_applied and neo_code._hermes_applied[0]["backup"]
        # 回滚
        out = neo_code.tool_hermes_apply(neo_code.SessionState(), action="rollback", entry_id="h9")
        assert "Rolled back" in out
        assert "某坑" not in target.read_text(encoding="utf-8")

    def test_apply_unverified_warns(self, tmp_path, monkeypatch):
        monkeypatch.setattr(neo_code, "_hermes_backups_dir", tmp_path / "backups")
        target = tmp_path / "D.md"
        target.write_text("x", encoding="utf-8")
        entry = {
            "id": "h8", "category": "preference", "title": "t", "detail": "d",
            "applies_when": "w", "strategy": "s", "target_file": str(target),
            "verified": False, "source_trajectory": "x",
        }
        monkeypatch.setattr(neo_code, "_hermes_pending", [dict(entry)])
        out = neo_code.tool_hermes_apply(neo_code.SessionState(), action="apply", entry_id="h8")
        assert "未通过确定性验证" in out


class TestOptimisticLock:
    def test_content_change_caught_with_same_mtime(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("v1", encoding="utf-8")
        neo_code._mark_file_read(f)
        # 改写内容但保持 mtime 不变（Windows 上 mtime 粒度粗，哈希兜底）
        f.write_text("v2", encoding="utf-8")
        st = f.stat()
        os.utime(f, (st.st_atime, st.st_atime))
        result = neo_code._check_file_read_before_edit(f)
        assert result is not None
        assert "changed" in result.lower() or "modified" in result.lower()

    def test_unchanged_passes(self, tmp_path):
        f = tmp_path / "b.txt"
        f.write_text("same", encoding="utf-8")
        neo_code._mark_file_read(f)
        assert neo_code._check_file_read_before_edit(f) is None


class TestCrossVerify:
    def test_no_client_returns_unverified(self):
        saved = neo_code._global_client
        try:
            neo_code._global_client = None
            out = neo_code._cross_verify("任务", "完成", [])
        finally:
            neo_code._global_client = saved
        assert "未验证" in out

    def test_reviewer_parses_verdict(self):
        client = MagicMock()
        client.flash_chat.return_value = json.dumps({"verdict": "pass", "reason": "有工具证据支撑"})
        saved = neo_code._global_client
        try:
            neo_code._global_client = client
            out = neo_code._cross_verify("任务", "完成", ["tool result ok"])
        finally:
            neo_code._global_client = saved
        assert "[Reviewer] pass" in out
