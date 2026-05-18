from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import uuid
from typing import Any


REQUIRED_TASK_FIELDS = ("id", "from", "to", "type", "task")


@dataclass(frozen=True)
class TaskMessage:
    id: str
    from_agent: str
    to: str
    type: str
    task: str
    payload: dict[str, Any] = field(default_factory=dict)
    reply_to: str | None = None
    created_at: str | None = None
    risk_level: str = "normal"
    max_hops: int = 3

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskMessage":
        missing = [field for field in REQUIRED_TASK_FIELDS if not data.get(field)]
        if missing:
            raise ValueError(f"missing required fields: {', '.join(missing)}")
        payload = data.get("payload") or {}
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        return cls(
            id=str(data["id"]),
            from_agent=str(data["from"]),
            to=str(data["to"]),
            type=str(data["type"]),
            task=str(data["task"]),
            payload=payload,
            reply_to=data.get("reply_to"),
            created_at=data.get("created_at"),
            risk_level=str(data.get("risk_level", "normal")),
            max_hops=int(data.get("max_hops", 3)),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "from": self.from_agent,
            "to": self.to,
            "type": self.type,
            "task": self.task,
            "payload": self.payload,
            "reply_to": self.reply_to,
            "created_at": self.created_at,
            "risk_level": self.risk_level,
            "max_hops": self.max_hops,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_task(raw: bytes | str) -> TaskMessage:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("task message must be a JSON object")
    return TaskMessage.from_dict(data)


def dump_json(data: dict[str, Any]) -> bytes:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def build_agent_prompt(task: TaskMessage, agent_id: str, extra_instruction: str = "") -> str:
    payload_json = json.dumps(task.as_dict(), ensure_ascii=False, indent=2)
    parts = [
        f"You are {agent_id}. You received an asynchronous AgentBus task from {task.from_agent}.",
        "",
        f"Task name: {task.task}",
        f"Message ID: {task.id}",
        f"Risk level: {task.risk_level}",
        "",
        "Full task JSON:",
        payload_json,
        "",
        "Handle the task and return a clear result.",
        "If the task involves irreversible side effects, deleting or overwriting files, commits/merges, external messages, production changes, money, or unclear credentials/permissions, do not execute it directly; return status=needs_approval and explain the exact operation needing user confirmation.",
        "Do not include secrets, tokens, cookies, or Authorization headers in the result.",
    ]
    if extra_instruction:
        parts.extend(["", "Extra instruction:", extra_instruction])
    return "\n".join(parts)


def build_result_message(
    task: TaskMessage,
    agent_id: str,
    status: str,
    result: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    message: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "request_id": task.id,
        "from": agent_id,
        "to": task.from_agent,
        "type": "task.result",
        "status": status,
        "reply_to": task.reply_to,
        "completed_at": utc_now(),
    }
    if result is not None:
        message["result"] = result
    if error is not None:
        message["error"] = error
    return message
