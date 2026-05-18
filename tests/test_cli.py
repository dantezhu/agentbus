import logging
from logging.handlers import RotatingFileHandler

import pytest

from agentbus.cli import build_parser, configure_logging


def test_parser_accepts_worker_run_with_config_only():
    parser = build_parser()

    args = parser.parse_args(["worker", "run", "--config", "~/.agentbus/config.toml"])

    assert args.command == "worker"
    assert args.worker_command == "run"
    assert args.config == "~/.agentbus/config.toml"
    assert not hasattr(args, "agent_id")
    assert not hasattr(args, "nats_url")


def test_parser_rejects_worker_cli_overrides():
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["worker", "run", "--config", "~/.agentbus/config.toml", "--agent-id", "code"])


def test_parser_accepts_task_publish_subcommand_with_config():
    parser = build_parser()

    args = parser.parse_args([
        "task",
        "publish",
        "--config",
        "~/.agentbus/config.toml",
        "code",
        "ping",
        '{"text":"hello"}',
        "--from-agent",
        "agent-main",
        "--reply-to",
        "agent.main.results",
    ])

    assert args.command == "task"
    assert args.task_command == "publish"
    assert args.target_agent == "code"
    assert args.task_name == "ping"
    assert args.payload_json == '{"text":"hello"}'
    assert args.config == "~/.agentbus/config.toml"
    assert args.from_agent == "agent-main"
    assert args.reply_to == "agent.main.results"
    assert not hasattr(args, "nats_url")


def test_configure_logging_creates_default_log_file_in_log_dir(tmp_path):
    log_dir = tmp_path / ".agentbus" / "logs"
    worker_log_file = log_dir / "agentbus-worker.log"

    configure_logging(log_dir=str(log_dir), log_max_bytes=100, log_backup_count=2, force=True)
    logging.getLogger("agentbus.test").info("hello agentbus log")

    for handler in logging.getLogger().handlers:
        handler.flush()

    assert worker_log_file.exists()
    assert "hello agentbus log" in worker_log_file.read_text()
    file_handlers = [handler for handler in logging.getLogger().handlers if isinstance(handler, RotatingFileHandler)]
    assert file_handlers[0].maxBytes == 100
    assert file_handlers[0].backupCount == 2
