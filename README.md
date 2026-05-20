# agentbus

`agentbus` is a small NATS JetStream based task bus for distributed agent programs.

It is designed for this architecture:

```text
coordinator agent / human entry point
  ↓ publishes task
public NATS JetStream server
  ↓ durable delivery
agentbus worker long-running process on each worker machine
  ↓ invokes configured agent command
worker publishes result message and ack/nak/term the task
```

## Design goals

- No bot-to-bot chat dependency.
- No direct inbound access needed for worker machines.
- Generic agent command integration through TOML `chat_cmd`.
- Worker and publisher configuration via TOML files.
- NATS subjects keep routing explicit and permissionable.
- Durable task delivery through JetStream, not plain fire-and-forget pub/sub.

## Requirements

Server side:

- `nats-server` with JetStream enabled.
- `nats` CLI for stream setup and debugging.
- A reachable TCP port for NATS clients. The examples use non-default `7678` instead of NATS default `4222`.

Worker side:

- Python >= 3.11.
- Network access from the worker machine to the NATS server.
- A one-shot agent command configured as TOML `chat_cmd`.

## Layout

```text
.
├── agentbus/
│   ├── __init__.py      package metadata
│   ├── cli.py           agentbus command-line entrypoint
│   ├── config.py        TOML configuration
│   ├── messages.py      task/result schema and prompt builder
│   ├── publish.py       task publishing helpers
│   ├── result.py        result reading helpers
│   └── worker.py        NATS JetStream worker runtime
├── config/
│   ├── agentbus.worker.example.toml
│   └── nats-server.conf
├── deploy/
│   ├── launchd/com.agentbus.worker.plist
│   ├── supervisor/agentbus-worker.conf
│   └── systemd/agentbus-worker.service
├── scripts/
│   └── stream-setup.sh
├── skills/
│   └── agentbus/SKILL.md
├── tests/
│   └── test_*.py
├── LICENSE
├── README.md
├── pyproject.toml
├── requirements-dev.txt
└── requirements.txt
```

## 1. Configure the NATS server

- [NATS server source and releases](https://github.com/nats-io/nats-server)
- [NATS CLI source and releases](https://github.com/nats-io/natscli)
- [Official NATS installation guide](https://docs.nats.io/running-a-nats-service/introduction/installation)

Simple install examples:

```bash
# macOS
brew install nats-server nats-io/nats-tools/nats

# Go toolchain
go install github.com/nats-io/nats-server/v2@latest
go install github.com/nats-io/natscli/nats@latest

# Linux packages / Docker / binaries
# See the official installation guide above for the current commands.
```

Verify both commands are available:

```bash
nats-server --version
nats --version
```

Copy the sample config to the server's NATS config path. The upstream systemd example uses `/etc/nats-server.conf`; some distro packages may use a different path, so match the service you install.

```bash
sudo mkdir -p /data/nats /etc/nats/tls
sudo cp config/nats-server.conf /etc/nats-server.conf
```

Edit the config before starting the server:

```bash
sudo $EDITOR /etc/nats-server.conf
```

At minimum, change these values:

```text
main password
coder password
reviewer password
client port, if `7678` is not appropriate
TLS cert/key paths, if public internet clients will connect
jetstream.store_dir, if /data/nats is not appropriate
```

Start the server with that config:

```bash
nats-server -c /etc/nats-server.conf
```

If you use a project-specific filename such as `/etc/nats/agentbus.conf`, start with that exact path instead:

```bash
nats-server -c /etc/nats/agentbus.conf
```

For service-managed deployments, make sure the service runs the same `-c` path and that its OS user can write to `jetstream.store_dir`.

The sample config defines three users:

```text
main   publishes tasks and subscribes to central results
coder   subscribes to agentbus.coder.tasks and publishes results
reviewer    subscribes to agentbus.reviewer.tasks and publishes results
```

It also enables JetStream:

```text
jetstream {
  store_dir: "/data/nats"
  max_mem_store: 256MiB
  max_file_store: 10GiB
}

accounts {
  AGENTBUS: {
    jetstream: enabled
    users: [ ... ]
  }
}
```

The top-level `jetstream` block turns on JetStream for the server. Because this sample uses named accounts, the `AGENTBUS` account must also have `jetstream: enabled`; otherwise stream creation fails with `JetStream not enabled for account (10039)`.

NATS stores JetStream data under a `jetstream/` child directory of `store_dir`, so this example writes data under `/data/nats/jetstream`. Avoid setting `store_dir` to a path that already ends in `jetstream`, or you will get a nested `jetstream/jetstream` directory.

### Domain and TLS

For public internet deployments, prefer a domain plus TLS. The domain is configured in DNS, not inside NATS. NATS only needs to know which certificate and key files to serve.

Example DNS setup:

```text
agentbus.example.com.  A     <server_public_ipv4>
agentbus.example.com.  AAAA  <server_public_ipv6, optional>
```

Example Let's Encrypt certificate flow on the server:

```bash
sudo certbot certonly --standalone -d agentbus.example.com
sudo install -m 0644 /etc/letsencrypt/live/agentbus.example.com/fullchain.pem /etc/nats/tls/fullchain.pem
sudo install -m 0600 /etc/letsencrypt/live/agentbus.example.com/privkey.pem /etc/nats/tls/privkey.pem
sudo chown -R nats:nats /etc/nats/tls 2>/dev/null || true
```

Then uncomment or add the TLS block in the NATS config file:

```text
tls {
  cert_file: "/etc/nats/tls/fullchain.pem"
  key_file: "/etc/nats/tls/privkey.pem"
}
```

The examples in this README use the normal non-TLS URL form:

```text
nats://main:main_password@agentbus.example.com:7678
```

If the TLS block is enabled, switch client URLs to `tls://`, for example:

```text
tls://main:main_password@agentbus.example.com:7678
```

For public internet deployments, avoid exposing non-TLS `nats://` connections. Use TLS or put the NATS client port behind a VPN/private network.

Important network notes:

- Expose the NATS client port, `7678` in these examples, only to machines that need to connect. The NATS default is `4222`; using a non-default port reduces scanner noise but is not a security boundary.
- Keep the monitoring port `8222` private or bind it only to localhost/VPN.

## 2. Create JetStream streams

After the NATS server is running, create the task and result streams.

Use a user with JetStream API permission. In the sample config, `main` has `$JS.API.>` access:

```bash
./scripts/stream-setup.sh 'nats://main:main_password@agentbus.example.com:7678'
```

This creates:

```text
AGENTBUS_TASKS     subjects: agentbus.*.tasks    max age: 7d
AGENTBUS_RESULTS   subjects: agentbus.*.results  max age: 30d
```

You can inspect the streams with:

```bash
nats --server 'nats://main:main_password@agentbus.example.com:7678' stream ls
nats --server 'nats://main:main_password@agentbus.example.com:7678' stream info AGENTBUS_TASKS
nats --server 'nats://main:main_password@agentbus.example.com:7678' stream info AGENTBUS_RESULTS
```

## 3. Install the worker

From PyPI:

```bash
python3 -m venv env
source env/bin/activate
pip install --upgrade pip
pip install agentbus
```

From a source checkout:

```bash
python3 -m venv env
source env/bin/activate
pip install --upgrade pip
pip install -e .
```

Requires Python >= 3.11. If `python3` points to an older interpreter on your machine, use a versioned command such as `python3.11` or `python3.14`.

For development and tests:

```bash
pip install -e ".[dev]"
python -m pytest tests -q
```

## 4. Configure the worker

Prefer a config file:

```bash
mkdir -p ~/.agentbus
cp config/agentbus.worker.example.toml ~/.agentbus/config.toml
$EDITOR ~/.agentbus/config.toml
chmod 600 ~/.agentbus/config.toml
```

If `--config` is omitted, `agentbus worker run` checks:

```text
./agentbus.toml
~/.agentbus/config.toml
/etc/agentbus/agentbus.toml
```

Required worker fields:

```toml
[agent]
id = "coder"
# {input} is required and marks where AgentBus inserts the generated prompt.
chat_cmd = ["agent-cli", "chat", "--oneshot", "{input}"]

[worker]
# Use tls:// instead if the server TLS block is enabled.
server_url = "nats://coder:coder_password@agentbus.example.com:7678"
```

A fuller example:

```toml
[agent]
id = "coder"
chat_cmd = ["agent-cli", "chat", "--oneshot", "{input}"]
extra_instruction = ""

[worker]
# Use tls:// instead if the server TLS block is enabled.
server_url = "nats://coder:coder_password@agentbus.example.com:7678"
task_timeout_seconds = 1800
max_task_bytes = 1048576
reconnect_time_wait_seconds = 2
max_reconnect_attempts = -1

[log]
dir = "~/.agentbus/logs"
max_bytes = 104857600
backup_count = 5

```

Worker routing fields and JetStream stream names are derived or fixed, not configured. This keeps worker config aligned with `agentbus task publish`, which also derives task and result subjects from agent ids. Multiple workers with the same `agent.id` are replicas of the same logical agent and share the same durable consumer/progress.

`chat_cmd` must be a TOML array of strings. AgentBus rejects string-form commands so the generated multi-line prompt is always inserted as one explicit argv argument, never shell-parsed.

```toml
# Prompt between flags.
chat_cmd = ["agent-cli", "run", "--prompt", "{input}", "--json"]

# Hermes example. Keep `-Q` before `-q`, or put it after `{input}`;
# `-q` must be followed immediately by the query text.
chat_cmd = ["hermes", "chat", "-Q", "-q", "{input}"]
```

AgentBus intentionally does not use environment variables for worker configuration. Put worker settings in TOML and pass `--config` when you do not want the default path.

## 5. Run the worker

Foreground mode:

```bash
agentbus worker run --config ~/.agentbus/config.toml
```

For long-running deployment, use one of the included templates:

```text
deploy/systemd/agentbus-worker.service
deploy/launchd/com.agentbus.worker.plist
deploy/supervisor/agentbus-worker.conf
```

Before installing a service, edit the template paths, user, working directory, and config path for the target machine.

## 6. Publish a task

Read the latest result in one terminal:

```bash
agentbus result get \
  --server-url 'nats://main:main_password@agentbus.example.com:7678' \
  --agent main
```

To keep watching after reading recent history, add `--watch`. `--limit` has the same meaning whether or not `--watch` is set: read the latest N stored results first.

```bash
agentbus result get \
  --server-url 'nats://main:main_password@agentbus.example.com:7678' \
  --agent main \
  --limit 20 \
  --watch
```

Publish a task in another terminal:

```bash
agentbus task publish \
  --server-url 'nats://main:main_password@agentbus.example.com:7678' \
  --to coder \
  --to reviewer \
  --from main \
  --reply-to main \
  'hello'
```

Publishing uses CLI arguments instead of a TOML file because it is a short one-shot command.

| Argument | Required | Meaning |
| --- | --- | --- |
| `--server-url` | yes | NATS server URL. |
| `--to` | yes | Target agent id. Repeat it to publish the same content to multiple agents; AgentBus publishes one task message per target. |
| `content` | yes | Final positional argument. Stored as a plain string at `payload.content`; pass JSON-like data as text and let the receiving agent interpret it. |
| `--from` | no, defaults to `main` | Sender agent id. |
| `--reply-to` | no, defaults to `--from` | Agent id whose result inbox receives the worker execution record. AgentBus derives `agentbus.<reply_to>.results`. |
| `--task-type` | no, defaults to `default` | Optional work classification. |

Examples:

```bash
agentbus task publish \
  --server-url 'nats://main:main_password@agentbus.example.com:7678' \
  --to coder \
  'hello'

agentbus task publish \
  --server-url 'nats://main:main_password@agentbus.example.com:7678' \
  --to coder \
  --task-type batch \
  '[{"url":"https://example.com"}]'
```

The `--to coder` and `--to reviewer` options map directly to these task subjects:

```text
agentbus.coder.tasks
agentbus.reviewer.tasks
```

If the target workers are running, `agentbus result get --agent main` should receive `task.result` messages from:

```text
agentbus.main.results
```

## Message subjects

Recommended convention:

Agent IDs are used literally in subjects.

```text
agentbus.<agent_id>.tasks       tasks for one worker agent
agentbus.<agent_id>.results     optional direct result subject per agent
agentbus.main.results           central result subject for the coordinator
agentbus.<agent_id>.heartbeat   optional health events
```

Examples:

```text
agentbus.coder.tasks
agentbus.reviewer.tasks
agentbus.main.results
```

## Task message

```json
{
  "id": "task-20260518-0001",
  "from": "main",
  "to": "coder",
  "reply_to": "main",
  "type": "task.request",
  "task_type": "review_pr",
  "payload": {
    "content": "Review PR org/repo#123"
  }
}
```

## Result message

```json
{
  "id": "result-uuid",
  "type": "task.result",
  "status": "completed",
  "task": {
    "id": "task-20260518-0001",
    "from": "main",
    "to": "coder",
    "reply_to": "main",
    "type": "task.request",
    "task_type": "review_pr",
    "payload": {
      "content": "Review PR org/repo#123"
    },
    "created_at": "2026-05-18T00:00:00+00:00"
  },
  "result": "...agent output...",
  "completed_at": "2026-05-18T00:00:00+00:00"
}
```

`result` messages are worker-generated execution records. Agent-to-agent business replies should still be sent as new `task` messages. The original task is embedded whole under `task`; top-level duplicate routing fields such as `request_id`, `from`, `to`, `worker`, and `reply_to` are intentionally omitted.

Recommended status values:

```text
completed
failed
needs_approval
```

## Logs

The worker writes logs both to stderr and to a rotating file. The default log file is:

```text
~/.agentbus/logs/agentbus-worker.log
```

Default rotation settings:

```text
max file size: 100MB
backup count: 5
```

The log directory is created automatically. Configure it with `[log].dir`, `[log].max_bytes`, and `[log].backup_count` in TOML.

## Ack behavior

```text
valid task + command succeeds and result is published       → ack
valid task + command exits non-zero and result is published → ack
invalid JSON / invalid task schema                          → term if available, otherwise ack
worker crashes before result publish                        → nak if available, then raise
```

## Security notes

- Use one NATS user per agent.
- Replace all sample passwords before running in a shared or public environment.
- Restrict each user to only the subjects it needs. Worker users still need JetStream API and ack publish permissions (`$JS.API.>` plus `$JS.ACK.>`) so pull consumers can fetch and acknowledge tasks.
- Use TLS for public NATS deployments.
- Keep monitoring/admin ports private.
- Store config files with `chmod 600` if credentials are embedded in `[worker].server_url`.
- Do not put tokens, cookies, or authorization headers in task payloads unless strictly necessary.
- Treat tasks that delete data, send external messages, deploy code, merge PRs, or spend money as approval-required.

## License

Apache License 2.0. See [LICENSE](LICENSE).
