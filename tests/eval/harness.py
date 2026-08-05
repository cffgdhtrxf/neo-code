"""轻量 Agent 任务评估环境。

对应《深入理解 AI Agent》第 6 章 Verifiers 的环境分层：
单轮环境 / 多轮工具调用环境 / 有状态环境。评估不依赖 LLM，
直接驱动真实工具实现，用可执行断言验证最终状态，并记录完整轨迹供回放。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
import time

import neo_code


@dataclass
class EvalEnv:
    """评估环境：持有工作目录、会话状态与轨迹记录。"""

    workdir: Path
    state: neo_code.SessionState = field(default_factory=neo_code.SessionState)
    trajectory: list = field(default_factory=list)

    def call(self, name: str, args: dict) -> str:
        """通过真实工具分发执行工具调用，并记录到轨迹。"""
        result = neo_code._execute_tool_safe(self.state, name, args, None)
        self.trajectory.append({"tool": name, "args": args, "result": result, "ts": time.time()})
        return result


@dataclass
class EvalTask:
    """评估任务：setup 准备环境，execute 执行动作，verify 返回失败原因列表（空 = 通过）。"""

    name: str
    setup: Callable[[EvalEnv], None]
    execute: Callable[[EvalEnv], None]
    verify: Callable[[EvalEnv], list]

    def run(self, env: EvalEnv) -> list:
        failures = []
        try:
            self.setup(env)
        except Exception as e:  # noqa: BLE001 - 评估边界，任何异常都应转为失败原因
            return [f"setup failed: {type(e).__name__}: {e}"]
        try:
            self.execute(env)
        except Exception as e:  # noqa: BLE001 - 评估边界
            failures.append(f"execute raised: {type(e).__name__}: {e}")
        try:
            failures.extend(self.verify(env))
        except Exception as e:  # noqa: BLE001 - 评估边界
            failures.append(f"verify raised: {type(e).__name__}: {e}")
        return failures
