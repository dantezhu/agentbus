from __future__ import annotations

import json
import os
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
    payload_json: str,
    reply_to: str,
    risk_level: str,
    max_hops: int,
) -> dict[str, Any]:
    payload = json.loads(payload_json)
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    target = normalize_target_agent(target_agent)
    return {
        "id": task_id,
        "from": from_agent,
        "to": f"agent-{target}",
        "type": "task.request",
        "task": task_name,
        "payload": payload,
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
    payload_json: str,
    from_agent: str,
    reply_to: str,
    task_id: str | None,
    risk_level: str,
    max_hops: int,
    subject: str | None,
    publisher: PublisherFn = nats_publisher,
) -> dict[str, Any]:
    if not nats_url:
        raise ValueError("nats_url is required; pass --nats-url or set NATS_URL")
    target = normalize_target_agent(target_agent)
    message = build_task_message(
        task_id=task_id or f"task-{uuid.uuid4()}",
        from_agent=from_agent,
        target_agent=target,
        task_name=task_name,
        payload_json=payload_json,
        reply_to=reply_to,
        risk_level=risk_level,
        max_hops=max_hops,
    )
    publish_subject = subject or f"agent.{target}.tasks"
    await publisher(nats_url, publish_subject, dump_json(message))
    return message


def nats_url_from_env() -> str | None:
    return os.environ.get("NATS_URL")
