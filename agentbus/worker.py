from __future__ import annotations

from dataclasses import dataclass
import asyncio
import logging
from typing import Awaitable, Callable, Protocol

from .config import WorkerConfig
from .messages import build_agent_prompt, build_result_message, dump_json, load_task

logger = logging.getLogger(__name__)


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

    If any command argument contains the literal ``{input}``, replace that
    placeholder with the full prompt. Otherwise append the prompt as the final
    argument for simple one-shot CLIs.
    """
    if any("{input}" in arg for arg in config.agent_chat_cmd):
        return tuple(arg.replace("{input}", prompt) for arg in config.agent_chat_cmd)
    return (*config.agent_chat_cmd, prompt)


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
            self.config.nats_url,
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
        try:
            if len(msg.data) > self.config.max_task_bytes:
                raise ValueError(f"message exceeds max task bytes: {len(msg.data)}")
            task = load_task(msg.data)
        except Exception:
            logger.exception("Invalid task payload; terminating message")
            if hasattr(msg, "term"):
                await msg.term()
            else:
                await msg.ack()
            return

        reply_to = task.reply_to or self.config.default_result_subject
        prompt = build_agent_prompt(task, self.config.agent_id, self.config.extra_instruction)
        try:
            process = await self.runner(prompt, self.config)
            if process.returncode == 0:
                result = build_result_message(task, self.config.agent_id, "completed", result=process.stdout.strip())
            else:
                err = process.stderr.strip() or process.stdout.strip() or f"Agent command exited with {process.returncode}"
                result = build_result_message(task, self.config.agent_id, "failed", error=err)
            await self.publish_result(reply_to, result)
            await msg.ack()
        except Exception:
            logger.exception("Worker crashed before result publish; requesting redelivery")
            if hasattr(msg, "nak"):
                await msg.nak()
            raise

    async def run_forever(self) -> None:
        if self._js is None:
            await self.connect()
        assert self._js is not None
        subject = self.config.task_subject or f"agent.{self.config.agent_id}.tasks"
        durable = self.config.consumer_name
        logger.info("AgentBus worker starting: subject=%s durable=%s stream=%s", subject, durable, self.config.stream)
        sub = await self._js.pull_subscribe(subject, durable=durable, stream=self.config.stream)
        while True:
            try:
                messages = await sub.fetch(1, timeout=5)
            except TimeoutError:
                continue
            except asyncio.TimeoutError:
                continue
            for msg in messages:
                await self.handle_message(msg)
