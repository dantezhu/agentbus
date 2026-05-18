import asyncio
import json

import pytest

from agentbus.publish import build_task_message, publish_task


def test_build_task_message_uses_explicit_arguments_only():
    message = build_task_message(
        task_id="task-1",
        from_agent="agent-main",
        target_agent="code",
        task_name="ping",
        payload_json='{"text":"hello"}',
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
        "payload": {"text": "hello"},
        "reply_to": "agent.main.results",
        "risk_level": "normal",
        "max_hops": 3,
    }


def test_build_task_message_rejects_non_object_payload():
    with pytest.raises(ValueError, match="payload must be a JSON object"):
        build_task_message(
            task_id="task-1",
            from_agent="agent-main",
            target_agent="code",
            task_name="ping",
            payload_json='["not", "object"]',
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
        payload_json='{"text":"hello"}',
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
