from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import tomllib
from typing import Any


@dataclass(frozen=True)
class WorkerConfig:
    agent_id: str
    server_url: str
    agent_chat_cmd: list[str]
    stream: str = "AGENT_TASKS"
    task_timeout_seconds: int = 1800
    extra_instruction: str = ""
    log_dir: str = "~/.agentbus/logs"
    log_max_bytes: int = 100 * 1024 * 1024
    log_backup_count: int = 5
    max_task_bytes: int = 1024 * 1024
    reconnect_time_wait_seconds: int = 2
    max_reconnect_attempts: int = -1

    @property
    def consumer_name(self) -> str:
        return self.agent_id

    @property
    def task_subject(self) -> str:
        return f"agentbus.{self.agent_id}.tasks"


DEFAULT_LOG_DIR = Path.home() / ".agentbus" / "logs"

DEFAULT_CONFIG_PATHS = (
    Path("./agentbus.toml"),
    Path.home() / ".agentbus" / "config.toml",
    Path("/etc/agentbus/agentbus.toml"),
)


SECTION_FIELD_MAP = {
    "agent": {
        "id": "agent_id",
        "chat_cmd": "agent_chat_cmd",
        "extra_instruction": "extra_instruction",
    },
    "nats": {
        "url": "server_url",
        "stream": "stream",
    },
    "worker": {
        "task_timeout_seconds": "task_timeout_seconds",
        "max_task_bytes": "max_task_bytes",
        "reconnect_time_wait_seconds": "reconnect_time_wait_seconds",
        "max_reconnect_attempts": "max_reconnect_attempts",
    },
    "log": {
        "dir": "log_dir",
        "max_bytes": "log_max_bytes",
        "backup_count": "log_backup_count",
    },
}


def normalize_agent_chat_cmd(value: Any) -> list[str]:
    if not (isinstance(value, list) and all(isinstance(item, str) for item in value)):
        raise ValueError("agent_chat_cmd must be a list of strings")
    if not any("{input}" in item for item in value):
        raise ValueError("agent_chat_cmd must include the literal {input} placeholder")
    return value


def load_config_file(path: str | os.PathLike[str]) -> WorkerConfig:
    return config_from_mapping(load_config_file_data(path))


def flatten_grouped_config(data: dict[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    unknown: list[str] = []
    for section, values in data.items():
        if section in SECTION_FIELD_MAP:
            if not isinstance(values, dict):
                raise ValueError(f"config section [{section}] must be a table")
            allowed = SECTION_FIELD_MAP[section]
            for key, value in values.items():
                target = allowed.get(key)
                if target is None:
                    unknown.append(key)
                else:
                    flattened[target] = value
        else:
            flattened[section] = values
    if unknown:
        raise ValueError(f"unknown config fields: {', '.join(sorted(unknown))}")
    return flattened


def load_config_file_data(path: str | os.PathLike[str]) -> dict[str, Any]:
    config_path = Path(path).expanduser()
    with config_path.open("rb") as fh:
        raw = tomllib.load(fh)
    return flatten_grouped_config(dict(raw))


def find_default_config_file() -> Path | None:
    for path in DEFAULT_CONFIG_PATHS:
        expanded = path.expanduser()
        if expanded.exists():
            return expanded
    return None


def config_from_mapping(data: dict[str, Any]) -> WorkerConfig:
    defaults = {
        "stream": "AGENT_TASKS",
        "task_timeout_seconds": 1800,
        "extra_instruction": "",
        "log_dir": str(DEFAULT_LOG_DIR),
        "log_max_bytes": 100 * 1024 * 1024,
        "log_backup_count": 5,
        "max_task_bytes": 1024 * 1024,
        "reconnect_time_wait_seconds": 2,
        "max_reconnect_attempts": -1,
    }
    allowed_fields = {
        "agent_id",
        "server_url",
        "stream",
        "agent_chat_cmd",
        "task_timeout_seconds",
        "extra_instruction",
        "log_dir",
        "log_max_bytes",
        "log_backup_count",
        "max_task_bytes",
        "reconnect_time_wait_seconds",
        "max_reconnect_attempts",
    }
    unknown = sorted(set(data) - allowed_fields)
    if unknown:
        raise ValueError(f"unknown config fields: {', '.join(unknown)}")

    merged = defaults | {k: v for k, v in data.items() if v is not None}
    missing = [key for key in ("agent_id", "server_url", "agent_chat_cmd") if not merged.get(key)]
    if missing:
        raise ValueError(f"missing required config fields: {', '.join(missing)}")

    agent_id = str(merged["agent_id"])
    return WorkerConfig(
        agent_id=agent_id,
        server_url=str(merged["server_url"]),
        agent_chat_cmd=normalize_agent_chat_cmd(merged["agent_chat_cmd"]),
        stream=str(merged["stream"]),
        task_timeout_seconds=int(merged["task_timeout_seconds"]),
        extra_instruction=str(merged["extra_instruction"]),
        log_dir=str(merged["log_dir"]),
        log_max_bytes=int(merged["log_max_bytes"]),
        log_backup_count=int(merged["log_backup_count"]),
        max_task_bytes=int(merged["max_task_bytes"]),
        reconnect_time_wait_seconds=int(merged["reconnect_time_wait_seconds"]),
        max_reconnect_attempts=int(merged["max_reconnect_attempts"]),
    )


def config_from_sources(*, config_path: str | os.PathLike[str] | None = None) -> WorkerConfig:
    path = Path(config_path).expanduser() if config_path else find_default_config_file()
    if path is None:
        raise ValueError("config file is required; pass --config or create ~/.agentbus/config.toml")
    return config_from_mapping(load_config_file_data(path))


def build_config(config_path: str | os.PathLike[str] | None) -> WorkerConfig:
    return config_from_sources(config_path=config_path)
