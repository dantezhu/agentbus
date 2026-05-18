import json

import pytest

from agentbus.messages import TaskMessage, build_agent_prompt, build_result_message, load_task


def test_load_task_requires_core_fields():
    with pytest.raises(ValueError) as exc:
        load_task(json.dumps({"id": "t1", "from": "agent-main"}))

    assert "missing required fields" in str(exc.value)
    assert "to" in str(exc.value)
    assert "task" in str(exc.value)


def test_build_agent_prompt_includes_payload_and_safety_boundary():
    task = TaskMessage(
        id="task-1",
        from_agent="agent-main",
        to="agent-code",
        type="task.request",
        task="review_pr",
        payload={"repo": "demo", "pr": 12},
        reply_to="agent.main.results",
        risk_level="normal",
    )

    prompt = build_agent_prompt(task, agent_id="agent-code", extra_instruction="Be concise.")

    assert "agent-code" in prompt
    assert "review_pr" in prompt
    assert '"pr": 12' in prompt
    assert "needs_approval" in prompt
    assert "Be concise." in prompt


def test_build_result_message_preserves_request_and_reply_target():
    task = TaskMessage(
        id="task-1",
        from_agent="agent-main",
        to="agent-code",
        type="task.request",
        task="ping",
        payload={},
        reply_to="agent.main.results",
    )

    result = build_result_message(task, agent_id="agent-code", status="completed", result="pong")

    assert result["request_id"] == "task-1"
    assert result["from"] == "agent-code"
    assert result["to"] == "agent-main"
    assert result["type"] == "task.result"
    assert result["status"] == "completed"
    assert result["result"] == "pong"
    assert result["reply_to"] == "agent.main.results"
