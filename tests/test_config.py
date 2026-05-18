import argparse

from pathlib import Path

import pytest

from agentbus.config import DEFAULT_CONFIG_PATHS, DEFAULT_LOG_DIR, WorkerConfig, build_config, config_from_sources, load_config_file


def test_default_paths_use_home_agentbus_directory():
    assert DEFAULT_CONFIG_PATHS[1] == DEFAULT_CONFIG_PATHS[1].home() / ".agentbus" / "config.toml"
    assert DEFAULT_LOG_DIR == DEFAULT_LOG_DIR.home() / ".agentbus" / "logs"


def test_load_config_file_supports_grouped_toml_sections(tmp_path):
    config_path = tmp_path / "agentbus.toml"
    config_path.write_text(
        """
[agent]
id = "code"
chat_cmd = ["agent-cli", "chat", "--oneshot"]
timeout_seconds = 900
extra_instruction = "Keep results concise."

[nats]
url = "nats://agent-code:secret@example:4222"
stream = "AGENT_TASKS"
durable = "agent-code"
task_subject = "agent.code.tasks"
default_result_subject = "agent.main.results"

[log]
dir = "~/custom-agentbus-logs"
max_bytes = 100000000
backup_count = 7

[limits]
max_payload_bytes = 2048

[connection]
reconnect_time_wait_seconds = 3
max_reconnect_attempts = -1
""".strip()
    )

    config = load_config_file(config_path)

    assert config == WorkerConfig(
        agent_id="code",
        nats_url="nats://agent-code:secret@example:4222",
        agent_chat_cmd=["agent-cli", "chat", "--oneshot"],
        stream="AGENT_TASKS",
        durable="agent-code",
        task_subject="agent.code.tasks",
        default_result_subject="agent.main.results",
        timeout_seconds=900,
        extra_instruction="Keep results concise.",
        log_dir="~/custom-agentbus-logs",
        log_max_bytes=100000000,
        log_backup_count=7,
        max_payload_bytes=2048,
        reconnect_time_wait_seconds=3,
        max_reconnect_attempts=-1,
    )


def test_config_precedence_cli_over_env_over_file(tmp_path):
    config_path = tmp_path / "agentbus.toml"
    config_path.write_text(
        """
[agent]
id = "file-agent"
chat_cmd = "agent-cli chat --oneshot"
timeout_seconds = 300

[nats]
url = "nats://file@example:4222"
stream = "FILE_STREAM"
""".strip()
    )

    args = argparse.Namespace(
        config=str(config_path),
        agent_id="cli-agent",
        nats_url=None,
        stream=None,
        subject="agent.cli.tasks",
        durable=None,
        log_dir=None,
        log_max_bytes=None,
        log_backup_count=None,
        log_level="INFO",
    )

    config = build_config(
        args,
        env={
            "NATS_URL": "nats://env@example:4222",
            "AGENT_TASK_TIMEOUT_SECONDS": "600",
        },
    )

    assert config.agent_id == "cli-agent"
    assert config.nats_url == "nats://env@example:4222"
    assert config.stream == "FILE_STREAM"
    assert config.task_subject == "agent.cli.tasks"
    assert config.agent_chat_cmd == ["agent-cli", "chat", "--oneshot"]
    assert config.timeout_seconds == 600


def test_agent_chat_cmd_is_required_and_unknown_names_are_rejected(tmp_path):
    missing_cmd = tmp_path / "missing.toml"
    missing_cmd.write_text(
        """
[agent]
id = "code"

[nats]
url = "nats://example:4222"
""".strip()
    )
    with pytest.raises(ValueError, match="agent_chat_cmd"):
        load_config_file(missing_cmd)

    old_name = tmp_path / "old.toml"
    old_name.write_text(
        """
[agent]
id = "code"
chat_cmd = "agent-cli"
old_cmd = "some-cmd"

[nats]
url = "nats://example:4222"
""".strip()
    )
    with pytest.raises(ValueError, match="unknown config fields: old_cmd"):
        load_config_file(old_name)

    with pytest.raises(ValueError, match="agent_id"):
        config_from_sources(env={"OLD_AGENT_ID": "code", "NATS_URL": "nats://example:4222", "AGENT_CHAT_CMD": "agent-cli"})


def test_example_worker_config_uses_grouped_sections_and_loads():
    config = load_config_file(Path("config/agentbus.worker.example.toml"))

    assert config.agent_id == "code"
    assert config.nats_url == "tls://username:password@agentbus.example.com:7422"
    assert config.agent_chat_cmd == ["agent-cli", "chat", "--oneshot", "{input}"]
    assert config.log_dir == "~/.agentbus/logs"
    assert config.log_max_bytes == 104857600
    assert config.log_backup_count == 5


def test_agent_prefixed_env_names_are_supported():
    config = config_from_sources(
        env={
            "AGENT_ID": "code",
            "NATS_URL": "nats://example:4222",
            "AGENT_CHAT_CMD": "other-agent run --prompt",
            "AGENTBUS_EXTRA_INSTRUCTION": "env instruction",
            "AGENTBUS_LOG_DIR": "~/env-agentbus-logs",
            "AGENTBUS_LOG_MAX_BYTES": "12345",
            "AGENTBUS_LOG_BACKUP_COUNT": "4",
            "AGENTBUS_MAX_PAYLOAD_BYTES": "4096",
        }
    )

    assert config.agent_id == "code"
    assert config.agent_chat_cmd == ["other-agent", "run", "--prompt"]
    assert config.extra_instruction == "env instruction"
    assert config.log_dir == "~/env-agentbus-logs"
    assert config.log_max_bytes == 12345
    assert config.log_backup_count == 4
    assert config.max_payload_bytes == 4096
