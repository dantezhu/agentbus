import json

import pytest

from agentbus.messages import TaskMessage, build_agent_prompt, build_result_message, load_task


def test_load_task_requires_core_fields():
    with pytest.raises(ValueError) as exc:
        load_task(json.dumps({"id": "t1", "from": "main"}))

    assert "missing required fields" in str(exc.value)
    assert "to" in str(exc.value)
    assert "task_type" in str(exc.value)


def test_build_agent_prompt_includes_payload_and_safety_boundary():
    task = TaskMessage(
        id="task-1",
        from_agent="main",
        to="coder",
        type="task.request",
        task_type="review_pr",
        payload={"repo": "demo", "pr": 12},
        reply_to="main",
    )

    prompt = build_agent_prompt(task, agent_id="coder", extra_instruction="Be concise.")

    assert "coder" in prompt
    assert "Task type: review_pr" in prompt
    assert '"pr": 12' in prompt
    assert "needs_approval" in prompt
    assert "Be concise." in prompt
    assert "Risk level" not in prompt


def test_build_result_message_embeds_task_context_without_duplicate_routing_fields():
    task = TaskMessage(
        id="task-1",
        from_agent="main",
        to="coder",
        type="task.request",
        task_type="ping",
        payload={"content": "hello"},
        reply_to="main",
        created_at="2026-05-18T00:00:00+00:00",
    )

    result = build_result_message(task, agent_id="coder", status="completed", result="pong")

    assert result["type"] == "task.result"
    assert result["status"] == "completed"
    assert result["result"] == "pong"
    assert result["task"] == {
        "id": "task-1",
        "from": "main",
        "to": "coder",
        "type": "task.request",
        "task_type": "ping",
        "payload": {"content": "hello"},
        "reply_to": "main",
        "created_at": "2026-05-18T00:00:00+00:00",
    }
    assert "request_id" not in result
    assert "from" not in result
    assert "to" not in result
    assert "worker" not in result
    assert "reply_to" not in result
