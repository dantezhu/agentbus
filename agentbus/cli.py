from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Callable
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TypeVar

from .config import build_config
from .publish import publish_tasks
from .result import read_results
from .worker import AgentBusWorker

T = TypeVar("T")


def run_interruptibly(parser: argparse.ArgumentParser, operation: Callable[[], T]) -> T:
    try:
        return operation()
    except KeyboardInterrupt:
        parser.exit(130)


def add_worker_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", help="Path to TOML config file")


def add_task_publish_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("content", help="Task content. Stored as payload.content")
    parser.add_argument("--server-url", required=True, help="Server connection URL, e.g. nats://user:pass@host:7422")
    parser.add_argument("--to", action="append", required=True, dest="to_agents", help="Target agent id. Repeat to publish to multiple agents")
    parser.add_argument("--task-type", required=True, help="Task type, e.g. ping or review_pr")
    parser.add_argument("--from", dest="from_agent", default="main", help="Sender agent id")
    parser.add_argument("--reply-to", help="Agent that should receive task results. Defaults to --from")


def add_result_get_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--server-url", required=True, help="Server connection URL, e.g. nats://user:pass@host:7422")
    parser.add_argument("--agent", required=True, help="Agent id whose result inbox should be read")
    parser.add_argument("--limit", type=int, default=1, help="Read the latest N stored results before exiting or watching")
    parser.add_argument("--watch", action="store_true", help="After reading the latest N stored results, keep watching new results")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgentBus command line interface", allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)

    worker_parser = subparsers.add_parser("worker", help="Worker commands", allow_abbrev=False)
    worker_subparsers = worker_parser.add_subparsers(dest="worker_command", required=True)
    worker_run_parser = worker_subparsers.add_parser("run", help="Run an AgentBus worker", allow_abbrev=False)
    add_worker_arguments(worker_run_parser)

    task_parser = subparsers.add_parser("task", help="Task commands", allow_abbrev=False)
    task_subparsers = task_parser.add_subparsers(dest="task_command", required=True)
    task_publish_parser = task_subparsers.add_parser("publish", help="Publish an AgentBus task", allow_abbrev=False)
    add_task_publish_arguments(task_publish_parser)

    result_parser = subparsers.add_parser("result", help="Result commands", allow_abbrev=False)
    result_subparsers = result_parser.add_subparsers(dest="result_command", required=True)
    result_get_parser = result_subparsers.add_parser("get", help="Read or watch AgentBus results", allow_abbrev=False)
    add_result_get_arguments(result_get_parser)
    return parser


def configure_logging(
    log_dir: str,
    *,
    log_max_bytes: int = 100 * 1024 * 1024,
    log_backup_count: int = 5,
    force: bool = False,
) -> None:
    path = Path(log_dir).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
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
    messages = await publish_tasks(
        server_url=args.server_url,
        target_agents=args.to_agents,
        task_type=args.task_type,
        content=args.content,
        from_agent=args.from_agent,
        reply_to=args.reply_to,
    )
    output = messages[0] if len(messages) == 1 else messages
    print(json.dumps(output, ensure_ascii=False, separators=(",", ":")))


def run_worker(args: argparse.Namespace) -> None:
    config = build_config(args.config)
    configure_logging(
        config.log_dir,
        log_max_bytes=config.log_max_bytes,
        log_backup_count=config.log_backup_count,
    )
    worker = AgentBusWorker(config)
    asyncio.run(worker.run_forever())


async def run_result_get(args: argparse.Namespace) -> None:
    await read_results(
        server_url=args.server_url,
        agent=args.agent,
        limit=args.limit,
        watch=args.watch,
        emit=lambda item: print(json.dumps(item, ensure_ascii=False, separators=(",", ":"))),
    )


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "worker" and args.worker_command == "run":
            run_interruptibly(parser, lambda: run_worker(args))
            return
        if args.command == "task" and args.task_command == "publish":
            run_interruptibly(parser, lambda: asyncio.run(run_task_publish(args)))
            return
        if args.command == "result" and args.result_command == "get":
            run_interruptibly(parser, lambda: asyncio.run(run_result_get(args)))
            return
    except Exception as exc:
        parser.exit(1, f"agentbus: error: {exc}\n")
    parser.error("unknown command")


if __name__ == "__main__":
    main(sys.argv[1:])
