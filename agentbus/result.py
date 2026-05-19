from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from .publish import build_result_subject

ConnectFn = Callable[[str], Awaitable[Any]]
EmitFn = Callable[[dict[str, Any]], None]


def _decode_message_data(data: bytes) -> dict[str, Any]:
    value = json.loads(data.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("result message must be a JSON object")
    return value


async def collect_recent_results(
    js: Any,
    subject: str,
    *,
    limit: int = 1,
    stream: str = "AGENT_RESULTS",
) -> list[dict[str, Any]]:
    """Return the latest N stored result messages for subject, oldest first.

    This is intentionally non-destructive: it reads stream history by sequence and
    does not create a durable consumer or ack result messages.
    """
    if limit <= 0:
        raise ValueError("limit must be positive")

    info = await js.stream_info(stream)
    last_seq = int(getattr(info.state, "last_seq", 0) or 0)
    results: list[dict[str, Any]] = []

    seq = last_seq
    while seq > 0 and len(results) < limit:
        try:
            msg = await js.get_msg(stream, seq=seq)
        except Exception:
            seq -= 1
            continue
        if getattr(msg, "subject", None) == subject:
            results.append(_decode_message_data(msg.data))
        seq -= 1

    results.reverse()
    return results


async def _default_connect(nats_url: str) -> Any:
    import nats

    return await nats.connect(nats_url)


async def read_results(
    *,
    nats_url: str,
    agent: str,
    limit: int = 1,
    watch: bool = False,
    stream: str = "AGENT_RESULTS",
    emit: EmitFn = print,
    connect: ConnectFn = _default_connect,
) -> None:
    if not nats_url:
        raise ValueError("nats_url is required")
    subject = build_result_subject(agent)
    nc = await connect(nats_url)
    try:
        js = nc.jetstream()
        for item in await collect_recent_results(js, subject, limit=limit, stream=stream):
            emit(item)

        if not watch:
            return

        sub = await nc.subscribe(subject)
        async for msg in sub.messages:
            emit(_decode_message_data(msg.data))
    finally:
        await nc.drain()
