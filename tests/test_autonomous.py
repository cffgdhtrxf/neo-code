"""自主驱动循环（实验版）测试：结构化决策、持久化调度、频率上限、定时触发。"""

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))
import neo_code


class TestExtractJson:
    def test_plain_json(self):
        assert neo_code._extract_json_object('{"a": 1}') == '{"a": 1}'

    def test_fenced_json(self):
        text = '```json\n{"should_initiate": true}\n```'
        assert neo_code._extract_json_object(text) == '{"should_initiate": true}'

    def test_prefix_suffix(self):
        text = 'Sure, here it is: {"x": 2} hope that helps'
        assert neo_code._extract_json_object(text) == '{"x": 2}'


class TestAutonomousDecide:
    def _client(self, payload):
        c = MagicMock()
        c.flash_chat.return_value = payload
        return c

    def test_valid_decision_parsed(self):
        client = self._client(json.dumps({
            "should_initiate": True, "delay_seconds": 3600,
            "topic_hint": "问工作进展", "tone": "caring", "reasoning": "用户提到压力",
        }))
        d = neo_code._autonomous_decide(client, "摘要")
        assert d["should_initiate"] is True
        assert d["delay_seconds"] == 3600
        assert d["topic_hint"] == "问工作进展"

    def test_delay_clamped(self):
        client = self._client(json.dumps({"should_initiate": True, "delay_seconds": 1}))
        d = neo_code._autonomous_decide(client, "摘要")
        assert d["delay_seconds"] >= neo_code._AUTONOMOUS_MIN_DELAY

    def test_garbage_refuses(self):
        client = self._client("not json at all")
        d = neo_code._autonomous_decide(client, "摘要")
        assert d["should_initiate"] is False
        assert "解析失败" in d["reasoning"]


class TestAutonomousTasks:
    def _setup(self, tmp_path, monkeypatch):
        tasks_path = tmp_path / "autonomous_tasks.jsonl"
        monkeypatch.setattr(neo_code, "_AUTONOMOUS_TASKS_PATH", tasks_path)
        return tasks_path

    def test_save_load_roundtrip(self, tmp_path, monkeypatch):
        path = self._setup(tmp_path, monkeypatch)
        neo_code._autonomous_save_task({"id": "a1", "status": "pending", "execute_at": time.time() + 100})
        neo_code._autonomous_save_task({"id": "a2", "status": "pending", "execute_at": time.time() + 200})
        tasks = neo_code._autonomous_load_tasks()
        assert len(tasks) == 2
        assert tasks[0]["id"] == "a1"

    def test_budget_respects_daily_max(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        now = time.time()
        for i in range(neo_code._AUTONOMOUS_MAX_PER_DAY):
            neo_code._autonomous_save_task({
                "id": f"d{i}", "status": "done", "sent": True,
                "triggered_at": now - 100 + i,
            })
        assert neo_code._autonomous_within_budget() is False

    def test_budget_respects_min_interval(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        neo_code._autonomous_save_task({
            "id": "recent", "status": "done", "sent": True,
            "triggered_at": time.time() - 10,
        })
        assert neo_code._autonomous_within_budget() is False

    def test_check_due_fires_event(self, tmp_path, monkeypatch):
        path = self._setup(tmp_path, monkeypatch)
        monkeypatch.setattr(neo_code, "_autonomous_user_turns", 0)
        monkeypatch.setattr(neo_code, "_global_client", None)
        neo_code._autonomous_save_task({
            "id": "due1", "status": "pending", "execute_at": time.time() - 1,
            "topic_hint": "聊聊近况", "tone": "casual",
            "user_turns_at_create": 0,
        })
        while not neo_code._event_queue.empty():
            neo_code._event_queue.get_nowait()
        neo_code._autonomous_check_due()
        events = neo_code._drain_events()
        assert "autonomous" in events
        assert "聊聊近况" in events
        tasks = neo_code._autonomous_load_tasks()
        assert tasks[0]["status"] == "done"
        assert tasks[0].get("sent") is True

    def test_cancelled_when_user_returned(self, tmp_path, monkeypatch):
        path = self._setup(tmp_path, monkeypatch)
        monkeypatch.setattr(neo_code, "_autonomous_user_turns", 1)
        neo_code._autonomous_save_task({
            "id": "c1", "status": "pending", "execute_at": time.time() - 1,
            "topic_hint": "不该发的", "tone": "casual", "user_turns_at_create": 0,
        })
        while not neo_code._event_queue.empty():
            neo_code._event_queue.get_nowait()
        neo_code._autonomous_check_due()
        assert neo_code._drain_events() == ""  # 用户已回来，静默取消
        tasks = neo_code._autonomous_load_tasks()
        assert tasks[0]["status"] == "cancelled"

    def test_chain_tick_continues_and_emits(self, tmp_path, monkeypatch):
        path = self._setup(tmp_path, monkeypatch)
        monkeypatch.setattr(neo_code, "_autonomous_user_turns", 0)
        client = MagicMock()
        client.flash_chat.return_value = json.dumps({
            "should_initiate": True, "delay_seconds": 600,
            "topic_hint": "跟进一下", "tone": "caring", "chain": True,
        })
        monkeypatch.setattr(neo_code, "_global_client", client)
        monkeypatch.setattr(neo_code, "_autonomous_adaptive_delay", lambda hour=None: 900)
        neo_code._autonomous_save_task({
            "id": "chain1", "kind": "chain", "status": "pending",
            "execute_at": time.time() - 1, "topic_hint": "旧话题",
            "tone": "casual", "summary": "摘要", "user_turns_at_create": 0,
        })
        while not neo_code._event_queue.empty():
            neo_code._event_queue.get_nowait()
        neo_code._autonomous_check_due()
        assert "跟进一下" in neo_code._drain_events()
        tasks = neo_code._autonomous_load_tasks()
        chain_next = [t for t in tasks if t.get("kind") == "chain" and t.get("status") == "pending"]
        assert len(chain_next) == 1  # 链式延续：产生下一个 pending 链式任务
        assert chain_next[0]["chain_depth"] == 1

    def test_chain_budget_stops_chain(self, tmp_path, monkeypatch):
        path = self._setup(tmp_path, monkeypatch)
        monkeypatch.setattr(neo_code, "_global_client", None)
        monkeypatch.setattr(neo_code, "_autonomous_chain_budget", lambda: False)
        neo_code._autonomous_save_task({
            "id": "c2", "kind": "chain", "status": "pending",
            "execute_at": time.time() - 1, "topic_hint": "t", "user_turns_at_create": 0,
        })
        while not neo_code._event_queue.empty():
            neo_code._event_queue.get_nowait()
        neo_code._autonomous_check_due()
        assert neo_code._drain_events() == ""
        tasks = neo_code._autonomous_load_tasks()
        assert not [t for t in tasks if t.get("status") == "pending"]  # 链式暂停

    def test_followup_redecides_no_send(self, tmp_path, monkeypatch):
        path = self._setup(tmp_path, monkeypatch)
        monkeypatch.setattr(neo_code, "_autonomous_user_turns", 0)
        client = MagicMock()
        client.flash_chat.return_value = json.dumps({
            "should_initiate": False, "reasoning": "现在不合适", "chain": False,
        })
        monkeypatch.setattr(neo_code, "_global_client", client)
        neo_code._autonomous_save_task({
            "id": "f1", "status": "pending", "execute_at": time.time() - 1,
            "topic_hint": "旧话题", "user_turns_at_create": 0,
        })
        while not neo_code._event_queue.empty():
            neo_code._event_queue.get_nowait()
        neo_code._autonomous_check_due()
        assert neo_code._drain_events() == ""  # 重决策说不发 → 不发
        tasks = neo_code._autonomous_load_tasks()
        assert tasks[0]["status"] == "done"
        assert not tasks[0].get("sent")

    def test_adaptive_delay_ranges(self):
        day = neo_code._autonomous_adaptive_delay(hour=12)
        assert neo_code._AUTONOMOUS_DAY_MIN_DELAY <= day <= neo_code._AUTONOMOUS_DAY_MAX_DELAY
        night = neo_code._autonomous_adaptive_delay(hour=3)
        assert neo_code._AUTONOMOUS_NIGHT_MIN_DELAY <= night <= neo_code._AUTONOMOUS_NIGHT_MAX_DELAY

    def test_maybe_schedule_persists_task(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        monkeypatch.setattr(neo_code, "_start_autonomous_poller", lambda: None)
        decision = {
            "should_initiate": True, "delay_seconds": 600,
            "topic_hint": "跟进面试", "tone": "caring",
        }
        monkeypatch.setattr(neo_code, "_autonomous_decide", lambda client, summary: decision)
        neo_code._autonomous_maybe_schedule(MagicMock(), MagicMock(), [{"role": "user", "content": "hi"}])
        tasks = neo_code._autonomous_load_tasks()
        assert len(tasks) == 1
        assert tasks[0]["topic_hint"] == "跟进面试"
        assert tasks[0]["status"] == "pending"
        assert tasks[0]["kind"] == "followup"

    def test_maybe_schedule_chain_kind(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        monkeypatch.setattr(neo_code, "_start_autonomous_poller", lambda: None)
        decision = {
            "should_initiate": True, "delay_seconds": 600,
            "topic_hint": "长期关心", "tone": "caring", "chain": True,
        }
        monkeypatch.setattr(neo_code, "_autonomous_decide", lambda client, summary: decision)
        neo_code._autonomous_maybe_schedule(MagicMock(), MagicMock(), [{"role": "user", "content": "hi"}])
        tasks = neo_code._autonomous_load_tasks()
        assert tasks[0]["kind"] == "chain"

    def test_maybe_schedule_refuse_sleeps(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        monkeypatch.setattr(
            neo_code, "_autonomous_decide",
            lambda client, summary: {"should_initiate": False, "reasoning": "不合适"},
        )
        neo_code._autonomous_maybe_schedule(MagicMock(), MagicMock(), [{"role": "user", "content": "hi"}])
        assert neo_code._autonomous_load_tasks() == []
