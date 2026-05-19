from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import uuid
from typing import Any


REQUIRED_TASK_FIELDS = ("id", "from", "to", "type", "task_type")

AGENT_PROMPT_INTRO_TEMPLATE = (
    "You are {agent_id}. You received an asynchronous AgentBus task from {from_agent}."
)

AGENT_PROMPT_TASK_CONTEXT_TEMPLATE = """\
Task type: {task_type}
Message ID: {message_id}

Full task JSON:
{payload_json}
"""

AGENT_PROMPT_DEFAULT_INSTRUCTIONS = """\
Handle the task and return a clear result.
By default, if the task involves irreversible side effects, deleting or overwriting files, commits/merges, external messages, production changes, money, or unclear credentials/permissions, do not execute it directly; return status=needs_approval and explain the exact operation needing user confirmation.
Do not include secrets, tokens, cookies, or Authorization headers in the result.
"""

EXTRA_INSTRUCTION_HEADER = "Extra instruction:"


@dataclass(frozen=True)
class TaskMessage:
    id: str
    from_agent: str
    to: str
    type: str
    task_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    reply_to: str | None = None
    created_at: str | None = None

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
            task_type=str(data["task_type"]),
            payload=payload,
            reply_to=data.get("reply_to"),
            created_at=data.get("created_at"),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "from": self.from_agent,
            "to": self.to,
            "reply_to": self.reply_to,
            "type": self.type,
            "task_type": self.task_type,
            "payload": self.payload,
            "created_at": self.created_at,
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
        AGENT_PROMPT_INTRO_TEMPLATE.format(
            agent_id=agent_id,
            from_agent=task.from_agent,
        ),
        "",
        AGENT_PROMPT_TASK_CONTEXT_TEMPLATE.format(
            task_type=task.task_type,
            message_id=task.id,
            payload_json=payload_json,
        ).strip(),
        "",
        AGENT_PROMPT_DEFAULT_INSTRUCTIONS.strip(),
    ]
    if extra_instruction:
        parts.extend(["", EXTRA_INSTRUCTION_HEADER, extra_instruction.strip()])
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
        "type": "task.result",
        "status": status,
        "task": task.as_dict(),
        "completed_at": utc_now(),
    }
    if result is not None:
        message["result"] = result
    if error is not None:
        message["error"] = error
    return message
