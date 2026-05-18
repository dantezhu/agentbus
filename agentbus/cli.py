from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import build_config
from .publish import nats_url_from_env, publish_task
from .worker import AgentBusWorker


def add_worker_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", help="Path to TOML config file")
    parser.add_argument("--agent-id", help="Agent id, e.g. code or doc. Overrides config file and AGENT_ID")
    parser.add_argument("--nats-url", help="NATS URL. Overrides config file and NATS_URL")
    parser.add_argument("--stream", help="JetStream stream name")
    parser.add_argument("--subject", help="Task subject to subscribe to")
    parser.add_argument("--durable", help="Durable consumer name")
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--log-dir", help="Log directory. Overrides config file and AGENTBUS_LOG_DIR")
    parser.add_argument("--log-max-bytes", type=int, help="Maximum bytes per worker log file before rotation")
    parser.add_argument("--log-backup-count", type=int, help="Number of rotated worker log files to keep")


def add_task_publish_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target_agent", help="Target agent id, e.g. code or agent-code")
    parser.add_argument("task_name", help="Task name, e.g. ping or review_pr")
    parser.add_argument("payload_json", nargs="?", default="{}", help="Task payload JSON object")
    parser.add_argument("--nats-url", default=nats_url_from_env(), help="NATS URL. Defaults to NATS_URL")
    parser.add_argument("--from-agent", default="agent-main", help="Sender agent id")
    parser.add_argument("--reply-to", default="agent.main.results", help="Result subject")
    parser.add_argument("--task-id", help="Explicit task id. Defaults to task-<uuid>")
    parser.add_argument("--risk-level", default="normal", help="Task risk level")
    parser.add_argument("--max-hops", type=int, default=3, help="Maximum delegation hops")
    parser.add_argument("--subject", help="Override publish subject. Defaults to agent.<target>.tasks")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgentBus command line interface")
    subparsers = parser.add_subparsers(dest="command", required=True)

    worker_parser = subparsers.add_parser("worker", help="Worker commands")
    worker_subparsers = worker_parser.add_subparsers(dest="worker_command", required=True)
    worker_run_parser = worker_subparsers.add_parser("run", help="Run an AgentBus worker")
    add_worker_arguments(worker_run_parser)

    task_parser = subparsers.add_parser("task", help="Task commands")
    task_subparsers = task_parser.add_subparsers(dest="task_command", required=True)
    task_publish_parser = task_subparsers.add_parser("publish", help="Publish an AgentBus task")
    add_task_publish_arguments(task_publish_parser)
    return parser


def configure_logging(
    log_level: str,
    log_dir: str,
    *,
    log_max_bytes: int = 100 * 1024 * 1024,
    log_backup_count: int = 5,
    force: bool = False,
) -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)
    path = Path(log_dir).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            RotatingFileHandler(
                path / "agentbus-worker.log",
                maxBytes=log_max_bytes,
                backupCount=log_backup_count,
                encoding="utf-8",
            ),
        ],
        force=force,
    )


async def run_task_publish(args: argparse.Namespace) -> None:
    message = await publish_task(
        nats_url=args.nats_url,
        target_agent=args.target_agent,
        task_name=args.task_name,
        payload_json=args.payload_json,
        from_agent=args.from_agent,
        reply_to=args.reply_to,
        task_id=args.task_id,
        risk_level=args.risk_level,
        max_hops=args.max_hops,
        subject=args.subject,
    )
    print(json.dumps(message, ensure_ascii=False, separators=(",", ":")))


def run_worker(args: argparse.Namespace) -> None:
    config = build_config(args)
    configure_logging(
        args.log_level,
        config.log_dir,
        log_max_bytes=config.log_max_bytes,
        log_backup_count=config.log_backup_count,
    )
    worker = AgentBusWorker(config)
    asyncio.run(worker.run_forever())


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "worker" and args.worker_command == "run":
            run_worker(args)
            return
        if args.command == "task" and args.task_command == "publish":
            asyncio.run(run_task_publish(args))
            return
    except Exception as exc:
        parser.exit(1, f"agentbus: error: {exc}\n")
    parser.error("unknown command")


if __name__ == "__main__":
    main(sys.argv[1:])
