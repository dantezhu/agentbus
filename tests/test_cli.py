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
        parser.parse_args(["worker", "run", "--config", "~/.agentbus/config.toml", "--agent-id", "coder"])


def test_parser_accepts_task_publish_subcommand_with_named_agent_args_and_positional_content():
    parser = build_parser()

    args = parser.parse_args([
        "task",
        "publish",
        "--nats-url",
        "nats://main:secret@agentbus.example.com:7422",
        "--to",
        "coder",
        "--to",
        "reviewer",
        "--task-type",
        "ping",
        "hello",
        "--from",
        "main",
        "--reply-to",
        "main",
    ])

    assert args.command == "task"
    assert args.task_command == "publish"
    assert args.to_agents == ["coder", "reviewer"]
    assert args.task_type == "ping"
    assert args.content == "hello"
    assert args.nats_url == "nats://main:secret@agentbus.example.com:7422"
    assert args.from_agent == "main"
    assert args.reply_to == "main"
    assert not hasattr(args, "payload_fmt")
    assert not hasattr(args, "task_fmt")
    assert not hasattr(args, "config")


def test_parser_rejects_task_publish_without_nats_url():
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["task", "publish", "--to", "coder", "--task-type", "ping", "hello"])


def test_parser_rejects_task_publish_without_named_target_or_task_type():
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args([
            "task",
            "publish",
            "--nats-url",
            "nats://main:secret@agentbus.example.com:7422",
            "coder",
            "ping",
            "hello",
        ])


def test_parser_rejects_removed_task_publish_options():
    parser = build_parser()

    removed_options = [
        "--task",
        "--subject",
        "--task-id",
        "--reply-to-agent",
        "--risk-level",
        "--max-hops",
        "--payload-fmt",
    ]
    for option in removed_options:
        with pytest.raises(SystemExit):
            parser.parse_args([
                "task",
                "publish",
                "--nats-url",
                "nats://main:secret@agentbus.example.com:7422",
                "--to",
                "coder",
                "--task-type",
                "ping",
                option,
                "value",
                "hello",
            ])


def test_parser_rejects_task_publish_config_file():
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["task", "publish", "--config", "~/.agentbus/main.toml", "--to", "coder", "--task-type", "ping", "hello"])


def test_parser_rejects_removed_task_fmt_option():
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args([
            "task",
            "publish",
            "--nats-url",
            "nats://main:secret@agentbus.example.com:7422",
            "--to",
            "coder",
            "--task-type",
            "ping",
            "--task-fmt",
            "json",
            "hello",
        ])


def test_parser_accepts_result_get_with_same_limit_for_watch_and_non_watch():
    parser = build_parser()

    args = parser.parse_args([
        "result",
        "get",
        "--nats-url",
        "nats://main:secret@agentbus.example.com:7422",
        "--agent",
        "main",
        "--limit",
        "20",
        "--watch",
    ])

    assert args.command == "result"
    assert args.result_command == "get"
    assert args.nats_url == "nats://main:secret@agentbus.example.com:7422"
    assert args.agent == "main"
    assert args.limit == 20
    assert args.watch is True
    assert not hasattr(args, "ack")


def test_parser_rejects_result_get_ack_option():
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args([
            "result",
            "get",
            "--nats-url",
            "nats://main:secret@agentbus.example.com:7422",
            "--agent",
            "main",
            "--ack",
        ])


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
