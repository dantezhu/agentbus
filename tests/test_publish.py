import asyncio
import json

import pytest

from agentbus.publish import build_task_message, publish_task, publish_tasks


def test_build_task_message_uses_agent_level_arguments_only():
    message = build_task_message(
        from_agent="main",
        target_agent="code",
        reply_to="coordinator",
        task_type="ping",
        content="hello",
    )

    assert message["id"].startswith("task-")
    assert message == {
        "id": message["id"],
        "from": "agent-main",
        "to": "agent-code",
        "type": "task.request",
        "task_type": "ping",
        "payload": {"fmt": "text", "content": "hello"},
        "reply_to": "agent-coordinator",
    }


def test_build_task_message_json_payload_fmt_wraps_any_json_value_as_payload_content():
    list_message = build_task_message(
        from_agent="main",
        target_agent="code",
        task_type="ping",
        content='[1, {"ok": true}]',
        payload_fmt="json",
    )
    string_message = build_task_message(
        from_agent="main",
        target_agent="code",
        task_type="ping",
        content='"hello"',
        payload_fmt="json",
    )

    assert list_message["payload"] == {"fmt": "json", "content": [1, {"ok": True}]}
    assert string_message["payload"] == {"fmt": "json", "content": "hello"}


def test_build_task_message_text_payload_fmt_accepts_empty_or_text_fmt():
    default_message = build_task_message(
        from_agent="main",
        target_agent="code",
        task_type="ping",
        content="hello",
    )
    empty_fmt_message = build_task_message(
        from_agent="main",
        target_agent="code",
        task_type="ping",
        content="hello",
        payload_fmt="",
    )

    assert default_message["payload"] == {"fmt": "text", "content": "hello"}
    assert empty_fmt_message["payload"] == {"fmt": "text", "content": "hello"}


def test_build_task_message_rejects_invalid_json_payload_fmt_content():
    with pytest.raises(ValueError, match="content must be valid JSON"):
        build_task_message(
            from_agent="main",
            target_agent="code",
            task_type="ping",
            content="{not-json}",
            payload_fmt="json",
        )


def test_build_task_message_rejects_unknown_payload_fmt():
    with pytest.raises(ValueError, match="payload_fmt must be text or json"):
        build_task_message(
            from_agent="main",
            target_agent="code",
            task_type="ping",
            content="hello",
            payload_fmt="xml",
        )


def test_build_task_message_defaults_reply_to_to_sender():
    message = build_task_message(
        from_agent="main",
        target_agent="code",
        task_type="ping",
        content="hello",
    )

    assert message["reply_to"] == "agent-main"


def test_build_task_message_rejects_empty_content():
    with pytest.raises(ValueError, match="content is required"):
        build_task_message(
            from_agent="main",
            target_agent="code",
            task_type="ping",
            content="",
        )


def test_publish_task_publishes_to_derived_subject_with_explicit_nats_url():
    published = []

    async def fake_publisher(nats_url, subject, payload):
        published.append((nats_url, subject, json.loads(payload.decode("utf-8"))))

    message = asyncio.run(publish_task(
        nats_url="tls://agent-main:secret@agentbus.example.com:7422",
        target_agent="code",
        task_type="ping",
        content="hello",
        from_agent="main",
        reply_to="coordinator",
        publisher=fake_publisher,
    ))

    assert message["id"].startswith("task-")
    assert message["reply_to"] == "agent-coordinator"
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
        task_type="ping",
        content="hello",
        from_agent="main",
        reply_to="coordinator",
        publisher=fake_publisher,
    ))

    assert [message["to"] for message in messages] == ["agent-code", "agent-doc"]
    assert [message["id"] for message in messages][0] != [message["id"] for message in messages][1]
    assert [message["reply_to"] for message in messages] == ["agent-coordinator", "agent-coordinator"]
    assert [subject for _, subject, _ in published] == ["agent.code.tasks", "agent.doc.tasks"]
    assert [payload for _, _, payload in published] == messages
