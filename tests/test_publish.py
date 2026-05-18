import asyncio
import json

import pytest

from agentbus.publish import build_task_message, publish_task, publish_tasks


def test_build_task_message_uses_explicit_arguments_only():
    message = build_task_message(
        task_id="task-1",
        from_agent="agent-main",
        target_agent="code",
        task_name="ping",
        content="hello",
        reply_to="agent.main.results",
        risk_level="normal",
        max_hops=3,
    )

    assert message == {
        "id": "task-1",
        "from": "agent-main",
        "to": "agent-code",
        "type": "task.request",
        "task": "ping",
        "payload": {"content": "hello"},
        "reply_to": "agent.main.results",
        "risk_level": "normal",
        "max_hops": 3,
    }


def test_build_task_message_rejects_empty_content():
    with pytest.raises(ValueError, match="content is required"):
        build_task_message(
            task_id="task-1",
            from_agent="agent-main",
            target_agent="code",
            task_name="ping",
            content="",
            reply_to="agent.main.results",
            risk_level="normal",
            max_hops=3,
        )


def test_publish_task_publishes_to_derived_subject_with_explicit_nats_url():
    published = []

    async def fake_publisher(nats_url, subject, payload):
        published.append((nats_url, subject, json.loads(payload.decode("utf-8"))))

    message = asyncio.run(publish_task(
        nats_url="tls://agent-main:secret@agentbus.example.com:7422",
        target_agent="code",
        task_name="ping",
        content="hello",
        from_agent="agent-main",
        reply_to="agent.main.results",
        task_id="task-1",
        risk_level="normal",
        max_hops=3,
        subject=None,
        publisher=fake_publisher,
    ))

    assert message["id"] == "task-1"
    assert published == [
        (
            "tls://agent-main:secret@agentbus.example.com:7422",
            "agent.code.tasks",
            message,
        )
    ]

def test_publish_tasks_publishes_one_message_per_target_agent():
    published = []

    async def fake_publisher(nats_url, subject, payload):
        published.append((nats_url, subject, json.loads(payload.decode("utf-8"))))

    messages = asyncio.run(publish_tasks(
        nats_url="tls://agent-main:secret@agentbus.example.com:7422",
        target_agents=["code", "doc"],
        task_name="ping",
        content="hello",
        from_agent="agent-main",
        reply_to="agent.main.results",
        task_id=None,
        risk_level="normal",
        max_hops=3,
        subject=None,
        publisher=fake_publisher,
    ))

    assert [message["to"] for message in messages] == ["agent-code", "agent-doc"]
    assert [subject for _, subject, _ in published] == ["agent.code.tasks", "agent.doc.tasks"]
    assert [payload for _, _, payload in published] == messages


def test_publish_tasks_rejects_subject_override_for_multiple_targets():
    async def fake_publisher(nats_url, subject, payload):
        raise AssertionError("should not publish")

    with pytest.raises(ValueError, match="subject override cannot be used with multiple target agents"):
        asyncio.run(publish_tasks(
            nats_url="tls://agent-main:secret@agentbus.example.com:7422",
            target_agents=["code", "doc"],
            task_name="ping",
            content="hello",
            from_agent="agent-main",
            reply_to="agent.main.results",
            task_id=None,
            risk_level="normal",
            max_hops=3,
            subject="agent.custom.tasks",
            publisher=fake_publisher,
        ))
