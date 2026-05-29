from __future__ import annotations

from dataclasses import dataclass
import asyncio
import logging
import time
from typing import Awaitable, Callable, Protocol

from .config import WorkerConfig
from .messages import build_agent_prompt, build_result_message, dump_json, load_task
from .publish import build_result_subject

logger = logging.getLogger(__name__)

TASK_STREAM = "AGENTBUS_TASKS"


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[str, WorkerConfig], Awaitable[ProcessResult]]


class Publisher(Protocol):
    async def publish(self, subject: str, payload: bytes) -> None: ...


def build_agent_command(prompt: str, config: WorkerConfig) -> tuple[str, ...]:
    """Build the configured agent command for one prompt.

    The command must contain the literal ``{input}`` placeholder. The config
    loader validates this, so execution is explicit instead of relying on an
    implicit final-argument append rule.
    """
    return tuple(arg.replace("{input}", prompt) for arg in config.agent_chat_cmd)


async def run_agent_chat(prompt: str, config: WorkerConfig) -> ProcessResult:
    proc = await asyncio.create_subprocess_exec(
        *build_agent_command(prompt, config),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=config.task_timeout_seconds)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return ProcessResult(returncode=124, stdout="", stderr=f"Agent command timed out after {config.task_timeout_seconds}s")
    return ProcessResult(
        returncode=proc.returncode or 0,
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
    )


class AgentBusWorker:
    def __init__(self, config: WorkerConfig, runner: Runner = run_agent_chat, publisher: Publisher | None = None):
        self.config = config
        self.runner = runner
        self.publisher = publisher
        self._nc = None
        self._js = None

    async def connect(self) -> None:
        import nats

        self._nc = await nats.connect(
            self.config.server_url,
            reconnect_time_wait=self.config.reconnect_time_wait_seconds,
            max_reconnect_attempts=self.config.max_reconnect_attempts,
        )
        self._js = self._nc.jetstream()
        self.publisher = self._nc

    async def close(self) -> None:
        if self._nc is not None:
            await self._nc.drain()

    async def publish_result(self, subject: str, result: dict) -> None:
        if self.publisher is None:
            raise RuntimeError("publisher is not configured")
        await self.publisher.publish(subject, dump_json(result))

    async def handle_message(self, msg) -> None:
        raw_size = len(msg.data)
        try:
            if raw_size > self.config.max_task_bytes:
                raise ValueError(f"message exceeds max task bytes: {raw_size}")
            task = load_task(msg.data)
        except Exception:
            logger.exception("worker event=task_invalid bytes=%s", raw_size)
            if hasattr(msg, "term"):
                await msg.term()
                logger.warning("worker event=task_terminated bytes=%s", raw_size)
            else:
                await msg.ack()
                logger.warning("worker event=task_acked_invalid bytes=%s", raw_size)
            return

        reply_to = build_result_subject(task.reply_to or task.from_agent)
        logger.info(
            "worker event=task_received task_id=%s from=%s to=%s task_type=%s reply_subject=%s bytes=%s",
            task.id,
            task.from_agent,
            task.to,
            task.task_type,
            reply_to,
            raw_size,
        )
        prompt = build_agent_prompt(task, self.config.agent_id, self.config.extra_instruction)
        logger.info(
            "worker event=task_processing_started task_id=%s agent=%s timeout_seconds=%s",
            task.id,
            self.config.agent_id,
            self.config.task_timeout_seconds,
        )
        started_at = time.monotonic()
        try:
            process = await self.runner(prompt, self.config)
            if process.returncode == 0:
                result = build_result_message(task, self.config.agent_id, "completed", result=process.stdout.strip())
            else:
                err = process.stderr.strip() or process.stdout.strip() or f"Agent command exited with {process.returncode}"
                result = build_result_message(task, self.config.agent_id, "failed", error=err)
            logger.info(
                "worker event=task_processing_finished task_id=%s status=%s returncode=%s duration_ms=%s stdout_bytes=%s stderr_bytes=%s",
                task.id,
                result["status"],
                process.returncode,
                int((time.monotonic() - started_at) * 1000),
                len(process.stdout.encode("utf-8")),
                len(process.stderr.encode("utf-8")),
            )
            logger.info(
                "worker event=result_publishing task_id=%s result_id=%s status=%s subject=%s",
                task.id,
                result["id"],
                result["status"],
                reply_to,
            )
            await self.publish_result(reply_to, result)
            logger.info(
                "worker event=result_published task_id=%s result_id=%s status=%s subject=%s",
                task.id,
                result["id"],
                result["status"],
                reply_to,
            )
            await msg.ack()
            logger.info("worker event=task_acked task_id=%s", task.id)
        except Exception:
            logger.exception("worker event=task_handle_failed task_id=%s action=redelivery", task.id)
            if hasattr(msg, "nak"):
                await msg.nak()
                logger.warning("worker event=task_nacked task_id=%s", task.id)
            raise

    async def run_forever(self) -> None:
        if self._js is None:
            await self.connect()
        assert self._js is not None
        subject = self.config.task_subject
        durable = self.config.consumer_name
        logger.info("AgentBus worker starting: subject=%s durable=%s stream=%s", subject, durable, TASK_STREAM)
        sub = await self._js.pull_subscribe(subject, durable=durable, stream=TASK_STREAM)
        try:
            while True:
                try:
                    messages = await sub.fetch(1, timeout=5)
                except (TimeoutError, asyncio.TimeoutError):
                    continue
                for msg in messages:
                    await self.handle_message(msg)
        finally:
            await self.close()
