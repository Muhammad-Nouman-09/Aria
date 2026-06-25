"""Offline test of the OpenRouter-style agent loop using a fake LLM.

Validates that the agent: emits the assistant message with `tool_calls`,
executes the tool, appends a `role:tool` result, then returns the model's
final text on the follow-up turn. No network / API key required.
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import get_settings  # noqa: E402
from core.agent import Agent  # noqa: E402

failures = []


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        failures.append(name)


def _tool_call(call_id, name, arguments):
    return SimpleNamespace(
        id=call_id, type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


class FakeLLM:
    """Turn 1: request get_system_info(cpu). Turn 2: final answer."""

    def __init__(self):
        self.calls = 0

    async def create(self, system, messages):
        self.calls += 1
        if self.calls == 1:
            return SimpleNamespace(
                content=None,
                tool_calls=[_tool_call("call_1", "get_system_info",
                                       '{"info_type": "cpu"}')],
            )
        return SimpleNamespace(
            content="Your CPU usage looks fine.", tool_calls=None)


async def main():
    s = get_settings()
    s.openrouter_api_key = "test-key-not-used"  # lets LLMClient construct
    agent = Agent(settings=s, approver=lambda a, p: True)
    agent.llm = FakeLLM()  # swap in the fake; no network

    reply = await agent.run("what's my cpu usage?")
    check("returns final text", reply == "Your CPU usage looks fine.")
    check("llm called twice", agent.llm.calls == 2)

    roles = [m["role"] for m in agent.messages]
    check("history has assistant turn", "assistant" in roles)
    check("history has tool result", "tool" in roles)

    assistant = next(m for m in agent.messages if m["role"] == "assistant")
    check("assistant carried tool_calls", "tool_calls" in assistant)
    tool_msg = next(m for m in agent.messages if m["role"] == "tool")
    check("tool result linked by id", tool_msg["tool_call_id"] == "call_1")
    check("tool actually ran (cpu percent in result)", "percent" in tool_msg["content"])

    agent.close()


asyncio.run(main())
print()
if failures:
    print(f"FAILED: {len(failures)} -> {failures}")
    sys.exit(1)
print("ALL AGENT-LOOP CHECKS PASSED")
