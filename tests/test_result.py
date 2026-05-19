import asyncio
import json

import pytest

from agentbus.result import build_result_subject, collect_recent_results, read_results


class FakeState:
    def __init__(self, last_seq):
        self.last_seq = last_seq


class FakeStreamInfo:
    def __init__(self, last_seq):
        self.state = FakeState(last_seq)


class FakeStoredMessage:
    def __init__(self, subject, payload):
        self.subject = subject
        self.data = json.dumps(payload).encode("utf-8")


class FakeJetStream:
    def __init__(self):
        self.messages = {
            1: FakeStoredMessage("agentbus.main.results", {"id": "old"}),
            2: FakeStoredMessage("agentbus.coder.results", {"id": "other"}),
            3: FakeStoredMessage("agentbus.main.results", {"id": "newer"}),
            4: FakeStoredMessage("agentbus.main.results", {"id": "newest"}),
        }

    async def stream_info(self, stream):
        assert stream == "AGENTBUS_RESULTS"
        return FakeStreamInfo(last_seq=4)

    async def get_msg(self, stream, seq):
        assert stream == "AGENTBUS_RESULTS"
        return self.messages[seq]


class FakeLiveMessage:
    def __init__(self, payload):
        self.data = json.dumps(payload).encode("utf-8")


class FakeSubscription:
    def __init__(self, live_messages, *, cancel_after_messages: bool = False):
        self.live_messages = list(live_messages)
        self.cancel_after_messages = cancel_after_messages

    @property
    def messages(self):
        return self._messages()

    async def _messages(self):
        for message in self.live_messages:
            yield message
        if self.cancel_after_messages:
            raise asyncio.CancelledError

class FakeNats:
    def __init__(self, *, cancel_watch: bool = False):
        self.jetstream_context = FakeJetStream()
        self.subscribed_subjects = []
        self.drained = False
        self.cancel_watch = cancel_watch

    def jetstream(self):
        return self.jetstream_context

    async def subscribe(self, subject):
        self.subscribed_subjects.append(subject)
        return FakeSubscription([FakeLiveMessage({"id": "live"})], cancel_after_messages=self.cancel_watch)

    async def drain(self):
        self.drained = True


def test_build_result_subject_uses_agent_id_literally():
    assert build_result_subject("main") == "agentbus.main.results"
    assert build_result_subject("foo-bar") == "agentbus.foo-bar.results"


@pytest.mark.parametrize("limit", [0, -1])
def test_collect_recent_results_rejects_non_positive_limit(limit):
    with pytest.raises(ValueError, match="limit must be positive"):
        asyncio.run(collect_recent_results(FakeJetStream(), "agentbus.main.results", limit=limit))


def test_collect_recent_results_returns_recent_n_for_subject_in_chronological_order():
    results = asyncio.run(collect_recent_results(FakeJetStream(), "agentbus.main.results", limit=2))

    assert [result["id"] for result in results] == ["newer", "newest"]


def test_read_results_uses_same_limit_before_watch_and_non_watch():
    nc = FakeNats()
    seen = []

    async def fake_connect(server_url):
        assert server_url == "nats://main:secret@agentbus.example.com:7422"
        return nc

    asyncio.run(read_results(
        server_url="nats://main:secret@agentbus.example.com:7422",
        agent="main",
        limit=2,
        watch=True,
        emit=seen.append,
        connect=fake_connect,
    ))

    assert [item["id"] for item in seen] == ["newer", "newest", "live"]
    assert nc.subscribed_subjects == ["agentbus.main.results"]
    assert nc.drained is True


def test_read_results_drains_connection_when_watch_is_cancelled():
    nc = FakeNats(cancel_watch=True)
    seen = []

    async def fake_connect(server_url):
        return nc

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(read_results(
            server_url="nats://main:secret@agentbus.example.com:7422",
            agent="main",
            limit=1,
            watch=True,
            emit=seen.append,
            connect=fake_connect,
        ))

    assert [item["id"] for item in seen] == ["newest", "live"]
    assert nc.drained is True
