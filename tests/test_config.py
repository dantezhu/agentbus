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
id = "coder"
chat_cmd = ["agent-cli", "chat", "--oneshot", "{input}"]
extra_instruction = "Keep results concise."

[worker]
task_timeout_seconds = 900
max_task_bytes = 2048
reconnect_time_wait_seconds = 3
max_reconnect_attempts = -1

[nats]
url = "nats://coder:secret@example:4222"
stream = "AGENT_TASKS"
durable = "coder"
task_subject = "agentbus.coder.tasks"
default_result_subject = "agentbus.main.results"

[log]
dir = "~/custom-agentbus-logs"
max_bytes = 100000000
backup_count = 7

""".strip()
    )

    config = load_config_file(config_path)

    assert config == WorkerConfig(
        agent_id="coder",
        nats_url="nats://coder:secret@example:4222",
        agent_chat_cmd=["agent-cli", "chat", "--oneshot", "{input}"],
        stream="AGENT_TASKS",
        durable="coder",
        task_subject="agentbus.coder.tasks",
        default_result_subject="agentbus.main.results",
        task_timeout_seconds=900,
        extra_instruction="Keep results concise.",
        log_dir="~/custom-agentbus-logs",
        log_max_bytes=100000000,
        log_backup_count=7,
        max_task_bytes=2048,
        reconnect_time_wait_seconds=3,
        max_reconnect_attempts=-1,
    )


def test_build_config_reads_config_file_without_env_or_cli_overrides(tmp_path, monkeypatch):
    config_path = tmp_path / "agentbus.toml"
    config_path.write_text(
        """
[agent]
id = "file-agent"
chat_cmd = ["agent-cli", "chat", "--oneshot", "{input}"]

[worker]
task_timeout_seconds = 300

[nats]
url = "nats://file@example:4222"
stream = "FILE_STREAM"
""".strip()
    )
    monkeypatch.setenv("NATS_URL", "nats://env@example:4222")
    monkeypatch.setenv("AGENT_ID", "env-agent")

    config = build_config(str(config_path))

    assert config.agent_id == "file-agent"
    assert config.nats_url == "nats://file@example:4222"
    assert config.stream == "FILE_STREAM"
    assert config.task_subject == "agentbus.file-agent.tasks"
    assert config.agent_chat_cmd == ["agent-cli", "chat", "--oneshot", "{input}"]
    assert config.task_timeout_seconds == 300


def test_agent_chat_cmd_is_required_and_unknown_names_are_rejected(tmp_path):
    missing_cmd = tmp_path / "missing.toml"
    missing_cmd.write_text(
        """
[agent]
id = "coder"

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
id = "coder"
chat_cmd = ["agent-cli", "{input}"]
old_cmd = "some-cmd"

[nats]
url = "nats://example:4222"
""".strip()
    )
    with pytest.raises(ValueError, match="unknown config fields: old_cmd"):
        load_config_file(old_name)


def test_agent_chat_cmd_must_be_list_of_strings(tmp_path):
    config_path = tmp_path / "string-chat-cmd.toml"
    config_path.write_text(
        """
[agent]
id = "coder"
chat_cmd = "agent-cli chat --oneshot {input}"

[nats]
url = "nats://example:4222"
""".strip()
    )

    with pytest.raises(ValueError, match="list of strings"):
        load_config_file(config_path)


def test_agent_chat_cmd_must_include_input_placeholder(tmp_path):
    config_path = tmp_path / "missing-placeholder.toml"
    config_path.write_text(
        """
[agent]
id = "coder"
chat_cmd = ["agent-cli", "chat", "--oneshot"]

[nats]
url = "nats://example:4222"
""".strip()
    )

    with pytest.raises(ValueError, match=r"literal \{input\} placeholder"):
        load_config_file(config_path)


def test_config_from_sources_requires_config_file_when_default_is_absent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("agentbus.config.DEFAULT_CONFIG_PATHS", (tmp_path / "missing.toml",))

    with pytest.raises(ValueError, match="config file is required"):
        config_from_sources()


def test_example_worker_config_uses_grouped_sections_and_loads():
    config = load_config_file(Path("config/agentbus.worker.example.toml"))

    assert config.agent_id == "coder"
    assert config.nats_url == "tls://username:password@agentbus.example.com:7422"
    assert config.agent_chat_cmd == ["agent-cli", "chat", "--oneshot", "{input}"]
    assert config.log_dir == "~/.agentbus/logs"
    assert config.log_max_bytes == 104857600
    assert config.log_backup_count == 5
