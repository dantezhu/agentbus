from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from .messages import dump_json

PublisherFn = Callable[[str, str, bytes], Awaitable[None]]


def require_agent_id(agent_id: str) -> str:
    agent = agent_id.strip()
    if not agent:
        raise ValueError("agent id is required")
    return agent


def build_task_subject(target_agent: str) -> str:
    return f"agentbus.{require_agent_id(target_agent)}.tasks"


def build_result_subject(agent_id: str) -> str:
    return f"agentbus.{require_agent_id(agent_id)}.results"


def build_payload(content: str) -> dict[str, Any]:
    return {"content": content}


def build_task_message(
    *,
    from_agent: str,
    target_agent: str,
    task_type: str,
    content: str,
    reply_to: str | None = None,
) -> dict[str, Any]:
    if not content:
        raise ValueError("content is required")
    if not task_type.strip():
        raise ValueError("task_type is required")

    target = require_agent_id(target_agent)
    sender = require_agent_id(from_agent)
    reply_agent = require_agent_id(reply_to or sender)
    return {
        "id": f"task-{uuid.uuid4()}",
        "from": sender,
        "to": target,
        "type": "task.request",
        "task_type": task_type,
        "payload": build_payload(content),
        "reply_to": reply_agent,
    }


async def nats_publisher(server_url: str, subject: str, payload: bytes) -> None:
    import nats

    nc = await nats.connect(server_url)
    try:
        await nc.publish(subject, payload)
        await nc.flush()
    finally:
        await nc.drain()


async def publish_task(
    *,
    server_url: str,
    target_agent: str,
    task_type: str,
    content: str,
    from_agent: str,
    reply_to: str | None = None,
    publisher: PublisherFn = nats_publisher,
) -> dict[str, Any]:
    if not server_url:
        raise ValueError("server_url is required")
    target = require_agent_id(target_agent)
    message = build_task_message(
        from_agent=from_agent,
        target_agent=target,
        task_type=task_type,
        content=content,
        reply_to=reply_to,
    )
    await publisher(server_url, build_task_subject(target), dump_json(message))
    return message


async def publish_tasks(
    *,
    server_url: str,
    target_agents: list[str],
    task_type: str,
    content: str,
    from_agent: str,
    reply_to: str | None = None,
    publisher: PublisherFn = nats_publisher,
) -> list[dict[str, Any]]:
    targets = [require_agent_id(target) for target in target_agents]
    if not targets:
        raise ValueError("at least one target agent is required")

    messages = []
    for target in targets:
        messages.append(await publish_task(
            server_url=server_url,
            target_agent=target,
            task_type=task_type,
            content=content,
            from_agent=from_agent,
            reply_to=reply_to,
            publisher=publisher,
        ))
    return messages
