from __future__ import annotations

import argparse
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import build_config
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgentBus command line interface")
    subparsers = parser.add_subparsers(dest="command", required=True)
    worker_parser = subparsers.add_parser("worker", help="Run an AgentBus worker")
    add_worker_arguments(worker_parser)
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


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config = build_config(args)
    configure_logging(
        args.log_level,
        config.log_dir,
        log_max_bytes=config.log_max_bytes,
        log_backup_count=config.log_backup_count,
    )
    worker = AgentBusWorker(config)
    asyncio.run(worker.run_forever())


if __name__ == "__main__":
    main()
