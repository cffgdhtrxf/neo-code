"""评估任务集：单轮 / 多轮工具链 / 有状态环境。

每项任务通过 EvalEnv 驱动真实工具实现，最终状态由可执行断言验证；
失败原因列表为空即通过。轨迹可供回放与失败分析。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import EvalEnv, EvalTask

import neo_code


def _require_trajectory(env, problems, expected_steps):
    if not env.trajectory:
        problems.append("无轨迹记录（评估环境未执行任何工具调用）")
    elif len(env.trajectory) < expected_steps:
        problems.append(f"轨迹不完整: {len(env.trajectory)} 步, 期望 ≥ {expected_steps}")


def test_single_turn_file_read(tmp_path):
    """SingleTurnEnv：单次工具调用 + 可执行断言。"""
    env = EvalEnv(tmp_path)
    f = env.workdir / "data.json"
    f.write_text('{"name": "cli", "count": 42}', encoding="utf-8")

    def execute(e):
        e.call("read_file", {"path": str(f)})

    def verify(e):
        problems = []
        _require_trajectory(e, problems, 1)
        if e.trajectory and '"count"' not in e.trajectory[-1]["result"]:
            problems.append("read_file 未返回 JSON 内容")
        return problems

    task = EvalTask("single_turn_file_read", setup=lambda e: None, execute=execute, verify=verify)
    assert task.run(env) == []


def test_tool_chain_read_edit_verify(tmp_path):
    """ToolEnv：多轮工具链（读 → 改 → 再读），验证最终文件状态与轨迹。"""
    neo_code.set_edit_confirm_mode("never")
    env = EvalEnv(tmp_path)
    f = env.workdir / "greeting.txt"
    f.write_text("hello world\n", encoding="utf-8")

    def execute(e):
        e.call("read_file", {"path": str(f)})
        e.call("edit_file", {"path": str(f), "old_text": "hello", "new_text": "goodbye"})
        e.call("read_file", {"path": str(f)})

    def verify(e):
        problems = []
        _require_trajectory(e, problems, 3)
        content = f.read_text(encoding="utf-8")
        if "goodbye" not in content:
            problems.append(f"编辑未生效: {content!r}")
        return problems

    task = EvalTask("read_edit_verify", setup=lambda e: None, execute=execute, verify=verify)
    assert task.run(env) == []


def test_stateful_read_before_edit_gate(tmp_path):
    """StatefulToolEnv：状态依赖行为——未读即改被拒绝，先读后改成功。"""
    neo_code.set_edit_confirm_mode("never")
    env = EvalEnv(tmp_path)
    f = env.workdir / "locked.txt"
    f.write_text("original", encoding="utf-8")

    def execute(e):
        r1 = e.call("edit_file", {"path": str(f), "old_text": "original", "new_text": "changed"})
        env._gate_result = r1
        e.call("read_file", {"path": str(f)})
        e.call("edit_file", {"path": str(f), "old_text": "original", "new_text": "changed"})

    def verify(e):
        problems = []
        if "Error" not in getattr(env, "_gate_result", ""):
            problems.append("未读即改应被安全门拒绝")
        if "changed" not in f.read_text(encoding="utf-8"):
            problems.append("先读后改应成功")
        return problems

    task = EvalTask("read_before_edit_gate", setup=lambda e: None, execute=execute, verify=verify)
    assert task.run(env) == []


def test_stateful_memory_crud(tmp_path, monkeypatch):
    """StatefulToolEnv：记忆增删改，验证持久化状态（隔离到临时文件）。"""
    mem_file = tmp_path / "memories.json"
    monkeypatch.setattr(neo_code, "_MEMORIES_PATH", mem_file)
    env = EvalEnv(tmp_path)

    def execute(e):
        e.call("update_memory", {"action": "create", "id": "pref1", "title": "preference", "content": "prefers Chinese"})
        e.call("update_memory", {"action": "update", "id": "pref1", "content": "prefers English"})
        e.call("update_memory", {"action": "delete", "id": "pref1"})

    def verify(e):
        problems = []
        _require_trajectory(e, problems, 3)
        memories = neo_code._load_memories()
        titles = [m.get("title") for m in memories.values()]
        if "preference" in titles:
            problems.append("记忆删除后仍存在")
        return problems

    task = EvalTask("memory_crud", setup=lambda e: None, execute=execute, verify=verify)
    assert task.run(env) == []


def test_command_run_and_verify(tmp_path):
    """ToolEnv：命令执行，验证输出与退出码（Windows/Linux 通用 echo）。"""
    env = EvalEnv(tmp_path)

    def execute(e):
        e.call("run_command", {"command": "echo eval_marker_42", "timeout": 10})

    def verify(e):
        problems = []
        _require_trajectory(e, problems, 1)
        result = e.trajectory[-1]["result"] if e.trajectory else ""
        if "eval_marker_42" not in result:
            problems.append(f"命令输出缺失标记: {result[:120]!r}")
        if "Exit code: 0" not in result:
            problems.append(f"命令退出码非 0: {result[:120]!r}")
        return problems

    task = EvalTask("command_run", setup=lambda e: None, execute=execute, verify=verify)
    assert task.run(env) == []
