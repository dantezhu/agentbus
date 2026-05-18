from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import os
import shlex
import tomllib
from typing import Any


@dataclass(frozen=True)
class WorkerConfig:
    agent_id: str
    nats_url: str
    agent_chat_cmd: list[str]
    stream: str = "AGENT_TASKS"
    durable: str | None = None
    task_subject: str | None = None
    default_result_subject: str = "agent.main.results"
    timeout_seconds: int = 1800
    extra_instruction: str = ""
    log_dir: str = "~/.agentbus/logs"
    log_max_bytes: int = 100 * 1024 * 1024
    log_backup_count: int = 5
    max_payload_bytes: int = 1024 * 1024
    reconnect_time_wait_seconds: int = 2
    max_reconnect_attempts: int = -1

    @classmethod
    def from_env(cls) -> "WorkerConfig":
        return config_from_sources(env=os.environ)

    @property
    def consumer_name(self) -> str:
        return self.durable or self.agent_id


DEFAULT_LOG_DIR = Path.home() / ".agentbus" / "logs"

DEFAULT_CONFIG_PATHS = (
    Path("./agentbus.toml"),
    Path.home() / ".agentbus" / "config.toml",
    Path("/etc/agentbus/agentbus.toml"),
)


def normalize_agent_chat_cmd(value: Any) -> list[str]:
    if isinstance(value, str):
        return shlex.split(value)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    raise ValueError("agent_chat_cmd must be a string or list of strings")


def load_config_file(path: str | os.PathLike[str]) -> WorkerConfig:
    return config_from_mapping(load_config_file_data(path))


def load_config_file_data(path: str | os.PathLike[str]) -> dict[str, Any]:
    config_path = Path(path).expanduser()
    with config_path.open("rb") as fh:
        raw = tomllib.load(fh)
    worker = raw.get("worker", raw)
    if not isinstance(worker, dict):
        raise ValueError("config file must contain a [worker] table or top-level mapping")
    return dict(worker)


def find_default_config_file() -> Path | None:
    for path in DEFAULT_CONFIG_PATHS:
        expanded = path.expanduser()
        if expanded.exists():
            return expanded
    return None


def env_config_data(env: os._Environ[str] | dict[str, str]) -> dict[str, Any]:
    mapping = {
        "AGENT_ID": "agent_id",
        "NATS_URL": "nats_url",
        "AGENTBUS_STREAM": "stream",
        "AGENTBUS_DURABLE": "durable",
        "AGENTBUS_TASK_SUBJECT": "task_subject",
        "AGENTBUS_DEFAULT_RESULT_SUBJECT": "default_result_subject",
        "AGENT_CHAT_CMD": "agent_chat_cmd",
        "AGENT_TASK_TIMEOUT_SECONDS": "timeout_seconds",
        "AGENTBUS_EXTRA_INSTRUCTION": "extra_instruction",
        "AGENTBUS_LOG_DIR": "log_dir",
        "AGENTBUS_LOG_MAX_BYTES": "log_max_bytes",
        "AGENTBUS_LOG_BACKUP_COUNT": "log_backup_count",
        "AGENTBUS_MAX_PAYLOAD_BYTES": "max_payload_bytes",
        "AGENTBUS_RECONNECT_WAIT_SECONDS": "reconnect_time_wait_seconds",
        "AGENTBUS_MAX_RECONNECT_ATTEMPTS": "max_reconnect_attempts",
    }
    return {key: env[env_name] for env_name, key in mapping.items() if env_name in env}


def config_from_mapping(data: dict[str, Any]) -> WorkerConfig:
    defaults = {
        "stream": "AGENT_TASKS",
        "default_result_subject": "agent.main.results",
        "timeout_seconds": 1800,
        "extra_instruction": "",
        "log_dir": str(DEFAULT_LOG_DIR),
        "log_max_bytes": 100 * 1024 * 1024,
        "log_backup_count": 5,
        "max_payload_bytes": 1024 * 1024,
        "reconnect_time_wait_seconds": 2,
        "max_reconnect_attempts": -1,
    }
    allowed_fields = {
        "agent_id",
        "nats_url",
        "stream",
        "durable",
        "task_subject",
        "default_result_subject",
        "agent_chat_cmd",
        "timeout_seconds",
        "extra_instruction",
        "log_dir",
        "log_max_bytes",
        "log_backup_count",
        "max_payload_bytes",
        "reconnect_time_wait_seconds",
        "max_reconnect_attempts",
    }
    unknown = sorted(set(data) - allowed_fields)
    if unknown:
        raise ValueError(f"unknown config fields: {', '.join(unknown)}")

    merged = defaults | {k: v for k, v in data.items() if v is not None}
    missing = [key for key in ("agent_id", "nats_url", "agent_chat_cmd") if not merged.get(key)]
    if missing:
        raise ValueError(f"missing required config fields: {', '.join(missing)}")

    agent_id = str(merged["agent_id"])
    durable = merged.get("durable")
    task_subject = merged.get("task_subject")
    return WorkerConfig(
        agent_id=agent_id,
        nats_url=str(merged["nats_url"]),
        agent_chat_cmd=normalize_agent_chat_cmd(merged["agent_chat_cmd"]),
        stream=str(merged["stream"]),
        durable=str(durable) if durable else agent_id,
        task_subject=str(task_subject) if task_subject else f"agent.{agent_id}.tasks",
        default_result_subject=str(merged["default_result_subject"]),
        timeout_seconds=int(merged["timeout_seconds"]),
        extra_instruction=str(merged["extra_instruction"]),
        log_dir=str(merged["log_dir"]),
        log_max_bytes=int(merged["log_max_bytes"]),
        log_backup_count=int(merged["log_backup_count"]),
        max_payload_bytes=int(merged["max_payload_bytes"]),
        reconnect_time_wait_seconds=int(merged["reconnect_time_wait_seconds"]),
        max_reconnect_attempts=int(merged["max_reconnect_attempts"]),
    )


def config_from_sources(
    *,
    config_path: str | os.PathLike[str] | None = None,
    env: os._Environ[str] | dict[str, str] | None = None,
    overrides: dict[str, Any] | None = None,
) -> WorkerConfig:
    data: dict[str, Any] = {}
    path = Path(config_path).expanduser() if config_path else find_default_config_file()
    if path is not None:
        data.update(load_config_file_data(path))
    if env is not None:
        data.update(env_config_data(env))
    if overrides:
        data.update({k: v for k, v in overrides.items() if v is not None})
    return config_from_mapping(data)


def build_config(args: argparse.Namespace, env: os._Environ[str] | dict[str, str] | None = None) -> WorkerConfig:
    overrides = {
        "agent_id": args.agent_id,
        "nats_url": args.nats_url,
        "stream": args.stream,
        "task_subject": args.subject,
        "durable": args.durable,
        "log_dir": args.log_dir,
        "log_max_bytes": args.log_max_bytes,
        "log_backup_count": args.log_backup_count,
    }
    return config_from_sources(config_path=args.config, env=os.environ if env is None else env, overrides=overrides)
