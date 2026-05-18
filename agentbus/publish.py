from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from .messages import dump_json

PublisherFn = Callable[[str, str, bytes], Awaitable[None]]


def normalize_target_agent(target_agent: str) -> str:
    target = target_agent.strip()
    if not target:
        raise ValueError("target agent is required")
    return target.removeprefix("agent-")


def build_task_message(
    *,
    task_id: str,
    from_agent: str,
    target_agent: str,
    task_name: str,
    content: str,
    reply_to: str,
    risk_level: str,
    max_hops: int,
) -> dict[str, Any]:
    if not content:
        raise ValueError("content is required")
    target = normalize_target_agent(target_agent)
    return {
        "id": task_id,
        "from": from_agent,
        "to": f"agent-{target}",
        "type": "task.request",
        "task": task_name,
        "payload": {"content": content},
        "reply_to": reply_to,
        "risk_level": risk_level,
        "max_hops": max_hops,
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
    task_name: str,
    content: str,
    from_agent: str,
    reply_to: str,
    task_id: str | None,
    risk_level: str,
    max_hops: int,
    subject: str | None,
    publisher: PublisherFn = nats_publisher,
) -> dict[str, Any]:
    if not nats_url:
        raise ValueError("nats_url is required")
    target = normalize_target_agent(target_agent)
    message = build_task_message(
        task_id=task_id or f"task-{uuid.uuid4()}",
        from_agent=from_agent,
        target_agent=target,
        task_name=task_name,
        content=content,
        reply_to=reply_to,
        risk_level=risk_level,
        max_hops=max_hops,
    )
    publish_subject = subject or f"agent.{target}.tasks"
    await publisher(nats_url, publish_subject, dump_json(message))
    return message

async def publish_tasks(
    *,
    nats_url: str,
    target_agents: list[str],
    task_name: str,
    content: str,
    from_agent: str,
    reply_to: str,
    task_id: str | None,
    risk_level: str,
    max_hops: int,
    subject: str | None,
    publisher: PublisherFn = nats_publisher,
) -> list[dict[str, Any]]:
    targets = [normalize_target_agent(target) for target in target_agents]
    if not targets:
        raise ValueError("at least one target agent is required")
    if subject and len(targets) > 1:
        raise ValueError("subject override cannot be used with multiple target agents")
    if task_id and len(targets) > 1:
        raise ValueError("task_id cannot be used with multiple target agents")

    messages = []
    for target in targets:
        messages.append(await publish_task(
            nats_url=nats_url,
            target_agent=target,
            task_name=task_name,
            content=content,
            from_agent=from_agent,
            reply_to=reply_to,
            task_id=task_id,
            risk_level=risk_level,
            max_hops=max_hops,
            subject=subject,
            publisher=publisher,
        ))
    return messages
