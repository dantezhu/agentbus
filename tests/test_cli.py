import logging
from logging.handlers import RotatingFileHandler

from agentbus.cli import build_parser, configure_logging


def test_parser_accepts_worker_run_subcommand_for_worker_options():
    parser = build_parser()

    args = parser.parse_args(["worker", "run", "--config", "~/.agentbus/config.toml", "--agent-id", "code"])

    assert args.command == "worker"
    assert args.worker_command == "run"
    assert args.config == "~/.agentbus/config.toml"
    assert args.agent_id == "code"


def test_parser_accepts_task_publish_subcommand():
    parser = build_parser()

    args = parser.parse_args([
        "task",
        "publish",
        "code",
        "ping",
        '{"text":"hello"}',
        "--nats-url",
        "tls://agent-main:secret@agentbus.example.com:7422",
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
    assert args.nats_url == "tls://agent-main:secret@agentbus.example.com:7422"
    assert args.from_agent == "agent-main"
    assert args.reply_to == "agent.main.results"


def test_configure_logging_creates_default_log_file_in_log_dir(tmp_path):
    log_dir = tmp_path / ".agentbus" / "logs"
    worker_log_file = log_dir / "agentbus-worker.log"

    configure_logging("INFO", log_dir=str(log_dir), log_max_bytes=100, log_backup_count=2, force=True)
    logging.getLogger("agentbus.test").info("hello agentbus log")

    for handler in logging.getLogger().handlers:
        handler.flush()

    assert worker_log_file.exists()
    assert "hello agentbus log" in worker_log_file.read_text()
    file_handlers = [handler for handler in logging.getLogger().handlers if isinstance(handler, RotatingFileHandler)]
    assert file_handlers[0].maxBytes == 100
    assert file_handlers[0].backupCount == 2
