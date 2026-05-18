from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from .messages import dump_json

PublisherFn = Callable[[str, str, bytes], Awaitable[None]]


def normalize_agent_id(agent_id: str) -> str:
    agent = agent_id.strip()
    if not agent:
        raise ValueError("agent id is required")
    return agent.removeprefix("agent-")


def build_task_subject(target_agent: str) -> str:
    return f"agent.{normalize_agent_id(target_agent)}.tasks"


def build_result_subject(reply_to_agent: str) -> str:
    return f"agent.{normalize_agent_id(reply_to_agent)}.results"


def build_payload(content: str, payload_fmt: str | None = "text") -> dict[str, Any]:
    fmt = payload_fmt or "text"
    if fmt == "text":
        return {"fmt": "text", "content": content}
    if fmt == "json":
        try:
            return {"fmt": "json", "content": json.loads(content)}
        except json.JSONDecodeError as exc:
            raise ValueError("content must be valid JSON when --payload-fmt json is used") from exc
    raise ValueError("payload_fmt must be text or json")


def build_task_message(
    *,
    from_agent: str,
    target_agent: str,
    task_type: str,
    content: str,
    payload_fmt: str | None = "text",
    reply_to_agent: str | None = None,
) -> dict[str, Any]:
    if not content:
        raise ValueError("content is required")
    if not task_type.strip():
        raise ValueError("task_type is required")

    target = normalize_agent_id(target_agent)
    sender = normalize_agent_id(from_agent)
    reply_agent = normalize_agent_id(reply_to_agent or sender)
    return {
        "id": f"task-{uuid.uuid4()}",
        "from": f"agent-{sender}",
        "to": f"agent-{target}",
        "reply_to_agent": f"agent-{reply_agent}",
        "type": "task.request",
        "task_type": task_type,
        "payload": build_payload(content, payload_fmt),
        "reply_to": build_result_subject(reply_agent),
    }


async def nats_publisher(nats_url: str, subject: str, payload: bytes) -> None:
    import nats

    nc = await nats.connect(nats_url)
    try:
        await nc.publish(subject, payload)
        await nc.flush()
    finally:
        await nc.drain()


async def publish_task(
    *,
    nats_url: str,
    target_agent: str,
    task_type: str,
    content: str,
    payload_fmt: str | None = "text",
    from_agent: str,
    reply_to_agent: str | None = None,
    publisher: PublisherFn = nats_publisher,
) -> dict[str, Any]:
    if not nats_url:
        raise ValueError("nats_url is required")
    target = normalize_agent_id(target_agent)
    message = build_task_message(
        from_agent=from_agent,
        target_agent=target,
        task_type=task_type,
        content=content,
        payload_fmt=payload_fmt,
        reply_to_agent=reply_to_agent,
    )
    await publisher(nats_url, build_task_subject(target), dump_json(message))
    return message


async def publish_tasks(
    *,
    nats_url: str,
    target_agents: list[str],
    task_type: str,
    content: str,
    payload_fmt: str | None = "text",
    from_agent: str,
    reply_to_agent: str | None = None,
    publisher: PublisherFn = nats_publisher,
) -> list[dict[str, Any]]:
    targets = [normalize_agent_id(target) for target in target_agents]
    if not targets:
        raise ValueError("at least one target agent is required")

    messages = []
    for target in targets:
        messages.append(await publish_task(
            nats_url=nats_url,
            target_agent=target,
            task_type=task_type,
            content=content,
            payload_fmt=payload_fmt,
            from_agent=from_agent,
            reply_to_agent=reply_to_agent,
            publisher=publisher,
        ))
    return messages
