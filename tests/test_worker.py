import asyncio
import json
import logging

import pytest

from agentbus.config import WorkerConfig
from agentbus.worker import AgentBusWorker, ProcessResult, build_agent_command, run_agent_chat


class DummyMsg:
    def __init__(self, payload):
        self.data = json.dumps(payload).encode("utf-8")
        self.acked = False
        self.nacked = False
        self.termed = False

    async def ack(self):
        self.acked = True

    async def nak(self):
        self.nacked = True

    async def term(self):
        self.termed = True


class DummyPublisher:
    def __init__(self):
        self.published = []

    async def publish(self, subject, payload):
        self.published.append((subject, json.loads(payload.decode("utf-8"))))


def make_config():
    return WorkerConfig(
        agent_id="coder",
        server_url="nats://example:4222",
        agent_chat_cmd=["agent-cli", "chat", "--oneshot", "{input}"],
    )


def test_handle_message_success_publishes_result_and_acks(caplog):
    payload = {
        "id": "task-1",
        "from": "main",
        "to": "coder",
        "type": "task.request",
        "task_type": "ping",
        "payload": {"x": 1},
        "reply_to": "main",
    }
    msg = DummyMsg(payload)
    publisher = DummyPublisher()

    async def runner(prompt, config):
        assert "ping" in prompt
        assert config.agent_id == "coder"
        return ProcessResult(returncode=0, stdout="pong\n", stderr="")

    async def scenario():
        worker = AgentBusWorker(make_config(), runner=runner, publisher=publisher)
        await worker.handle_message(msg)

    with caplog.at_level(logging.INFO, logger="agentbus.worker"):
        asyncio.run(scenario())

    assert msg.acked is True
    assert publisher.published[0][0] == "agentbus.main.results"
    result = publisher.published[0][1]
    assert result["status"] == "completed"
    assert result["result"] == "pong"
    assert result["task"]["id"] == "task-1"
    assert result["task"]["task_type"] == "ping"
    assert result["task"]["payload"] == {"x": 1}
    assert "request_id" not in result
    assert "from" not in result
    assert "to" not in result
    assert "worker" not in result
    assert "reply_to" not in result
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "event=task_received task_id=task-1" in logs
    assert "event=task_processing_started task_id=task-1" in logs
    assert "event=task_processing_finished task_id=task-1 status=completed returncode=0" in logs
    assert "event=result_published task_id=task-1" in logs
    assert "event=task_acked task_id=task-1" in logs
    assert "pong" not in logs


def test_handle_message_failed_agent_run_publishes_failed_result_and_acks():
    payload = {
        "id": "task-2",
        "from": "main",
        "to": "coder",
        "type": "task.request",
        "task_type": "fail",
        "payload": {},
    }
    msg = DummyMsg(payload)
    publisher = DummyPublisher()

    async def runner(prompt, config):
        return ProcessResult(returncode=2, stdout="", stderr="boom")

    async def scenario():
        worker = AgentBusWorker(make_config(), runner=runner, publisher=publisher)
        await worker.handle_message(msg)

    asyncio.run(scenario())

    assert msg.acked is True
    assert publisher.published[0][0] == "agentbus.main.results"
    result = publisher.published[0][1]
    assert result["status"] == "failed"
    assert result["error"] == "boom"


def test_invalid_payload_is_terminated_without_publish(caplog):
    msg = DummyMsg({"id": "bad"})
    publisher = DummyPublisher()

    async def scenario():
        worker = AgentBusWorker(make_config(), publisher=publisher)
        await worker.handle_message(msg)

    with caplog.at_level(logging.INFO, logger="agentbus.worker"):
        asyncio.run(scenario())

    assert msg.termed is True
    assert publisher.published == []
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "event=task_invalid" in logs
    assert "event=task_terminated" in logs


def test_run_agent_chat_uses_configured_command(monkeypatch):
    calls = {}

    class FakeProc:
        returncode = 0

        async def communicate(self):
            return b"ok", b""

    async def fake_create_subprocess_exec(*args, stdout, stderr):
        calls["args"] = args
        return FakeProc()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_create_subprocess_exec)

    result = asyncio.run(run_agent_chat("hello", make_config()))

    assert calls["args"] == ("agent-cli", "chat", "--oneshot", "hello")
    assert result.returncode == 0
    assert result.stdout == "ok"


def test_build_agent_command_replaces_input_placeholder_without_forcing_last_arg():
    config = WorkerConfig(
        agent_id="coder",
        server_url="nats://example:4222",
        agent_chat_cmd=["agent-cli", "run", "--prompt", "{input}", "--json"],
    )

    assert build_agent_command("hello world", config) == (
        "agent-cli",
        "run",
        "--prompt",
        "hello world",
        "--json",
    )


def test_run_forever_closes_nats_connection_when_cancelled():
    class FakeNatsConnection:
        def __init__(self):
            self.drained = False

        async def drain(self):
            self.drained = True

    class FakeSubscription:
        async def fetch(self, count, timeout):
            raise asyncio.CancelledError

    class FakeJetStream:
        async def pull_subscribe(self, subject, *, durable, stream):
            return FakeSubscription()

    async def scenario():
        worker = AgentBusWorker(make_config())
        worker._nc = FakeNatsConnection()
        worker._js = FakeJetStream()

        with pytest.raises(asyncio.CancelledError):
            await worker.run_forever()

        return worker._nc.drained

    assert asyncio.run(scenario()) is True


def test_run_forever_derives_subject_and_durable_from_agent_id():
    class FakeSubscription:
        async def fetch(self, count, timeout):
            raise asyncio.CancelledError

    class FakeJetStream:
        def __init__(self):
            self.calls = []

        async def pull_subscribe(self, subject, *, durable, stream):
            self.calls.append({"subject": subject, "durable": durable, "stream": stream})
            return FakeSubscription()

    async def scenario():
        worker = AgentBusWorker(make_config())
        worker._js = FakeJetStream()

        with pytest.raises(asyncio.CancelledError):
            await worker.run_forever()

        return worker._js.calls

    assert asyncio.run(scenario()) == [
        {"subject": "agentbus.coder.tasks", "durable": "coder", "stream": "AGENTBUS_TASKS"}
    ]
