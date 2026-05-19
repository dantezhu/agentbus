import asyncio
import json

import pytest

from agentbus.publish import build_task_message, publish_task, publish_tasks


def test_build_task_message_uses_agent_level_arguments_only():
    message = build_task_message(
        from_agent="main",
        target_agent="coder",
        reply_to="main",
        task_type="ping",
        content="hello",
    )

    assert message["id"].startswith("task-")
    assert message == {
        "id": message["id"],
        "from": "main",
        "to": "coder",
        "type": "task.request",
        "task_type": "ping",
        "payload": {"content": "hello"},
        "reply_to": "main",
    }


def test_build_task_message_stores_content_as_string_without_payload_format():
    message = build_task_message(
        from_agent="main",
        target_agent="coder",
        task_type="ping",
        content='[1, {"ok": true}]',
    )

    assert message["payload"] == {"content": '[1, {"ok": true}]'}


def test_build_task_message_defaults_reply_to_to_sender():
    message = build_task_message(
        from_agent="main",
        target_agent="coder",
        task_type="ping",
        content="hello",
    )

    assert message["reply_to"] == "main"


def test_build_task_message_rejects_empty_content():
    with pytest.raises(ValueError, match="content is required"):
        build_task_message(
            from_agent="main",
            target_agent="coder",
            task_type="ping",
            content="",
        )


def test_publish_task_publishes_to_derived_subject_with_explicit_nats_url():
    published = []

    async def fake_publisher(nats_url, subject, payload):
        published.append((nats_url, subject, json.loads(payload.decode("utf-8"))))

    message = asyncio.run(publish_task(
        nats_url="nats://main:secret@agentbus.example.com:7422",
        target_agent="coder",
        task_type="ping",
        content="hello",
        from_agent="main",
        reply_to="main",
        publisher=fake_publisher,
    ))

    assert message["id"].startswith("task-")
    assert message["reply_to"] == "main"
    assert published == [
        (
            "nats://main:secret@agentbus.example.com:7422",
            "agentbus.coder.tasks",
            message,
        )
    ]


def test_publish_tasks_publishes_one_message_per_target_agent():
    published = []

    async def fake_publisher(nats_url, subject, payload):
        published.append((nats_url, subject, json.loads(payload.decode("utf-8"))))

    messages = asyncio.run(publish_tasks(
        nats_url="nats://main:secret@agentbus.example.com:7422",
        target_agents=["coder", "reviewer"],
        task_type="ping",
        content="hello",
        from_agent="main",
        reply_to="main",
        publisher=fake_publisher,
    ))

    assert [message["to"] for message in messages] == ["coder", "reviewer"]
    assert [message["id"] for message in messages][0] != [message["id"] for message in messages][1]
    assert [message["reply_to"] for message in messages] == ["main", "main"]
    assert [subject for _, subject, _ in published] == ["agentbus.coder.tasks", "agentbus.reviewer.tasks"]
    assert [payload for _, _, payload in published] == messages
