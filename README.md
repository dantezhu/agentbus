# agentbus

`agentbus` is a small NATS JetStream based task bus for distributed agent programs.

It implements the option-B architecture:

```text
public NATS JetStream server
  ↓
agentbus-worker long-running process on each worker machine
  ↓
worker receives task messages and invokes a configured agent command
  ↓
worker publishes result messages and ack/nak/term the task
```

## Design goals

- No bot-to-bot chat dependency.
- No direct inbound access needed for worker machines.
- Generic agent command integration through `agent_chat_cmd`.
- Worker configuration via TOML file, with env/CLI overrides.
- NATS subjects keep routing explicit and permissionable.

## License

Apache License 2.0. See [LICENSE](LICENSE).

## Layout

```text
agentbus/
  config.py      TOML/env/CLI configuration
  messages.py    task/result schema and prompt builder
  worker.py      NATS JetStream worker runtime
  cli.py         agentbus-worker entrypoint
config/
  agentbus.worker.example.toml
  nats-server.conf
scripts/
  stream-setup.sh
  publish-task.sh
deploy/
  systemd/agentbus-worker.service
  launchd/com.agentbus.worker.plist
skills/
  agentbus/SKILL.md
```

## Message subjects

Recommended convention:

```text
agent.<agent_id>.tasks       tasks for one worker agent
agent.<agent_id>.results     optional direct result stream per agent
agent.main.results           central result subject for the coordinator
agent.<agent_id>.heartbeat   optional health events
```

Examples:

```text
agent.code.tasks
agent.doc.tasks
agent.main.results
```

## Task message

```json
{
  "id": "task-20260518-0001",
  "from": "agent-main",
  "to": "agent-code",
  "type": "task.request",
  "task": "review_pr",
  "payload": {
    "repo": "org/repo",
    "pr": 123
  },
  "reply_to": "agent.main.results",
  "risk_level": "normal",
  "max_hops": 3
}
```

## Result message

```json
{
  "id": "result-uuid",
  "request_id": "task-20260518-0001",
  "from": "agent-code",
  "to": "agent-main",
  "type": "task.result",
  "status": "completed",
  "result": "...agent output...",
  "reply_to": "agent.main.results",
  "completed_at": "2026-05-18T00:00:00+00:00"
}
```

Valid status values are free-form for now, but recommended values are:

```text
completed
failed
needs_approval
```

## Installation

Use a standard `venv` + `pip` setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

Requires Python >= 3.11. If `python3` points to an older interpreter on your machine, use a versioned command such as `python3.11` or `python3.14`.

For development and tests:

```bash
python -m pip install -e ".[dev]"
python -m pytest tests -q
```

## Worker config

Prefer a config file:

```bash
mkdir -p ~/.agentbus
cp config/agentbus.worker.example.toml ~/.agentbus/config.toml
$EDITOR ~/.agentbus/config.toml
chmod 600 ~/.agentbus/config.toml

agentbus-worker --config ~/.agentbus/config.toml
```

If `--config` is omitted, `agentbus-worker` checks:

```text
./agentbus.toml
~/.agentbus/config.toml
/etc/agentbus/agentbus.toml
```

Required worker fields:

```toml
[worker]
agent_id = "code"
nats_url = "nats://username:password@server_host:server_port"
agent_chat_cmd = ["agent-cli", "chat", "--oneshot"]
log_dir = "~/.agentbus/logs"
log_max_bytes = 104857600
log_backup_count = 5
```

`agent_chat_cmd` can be a string or a list:

```toml
agent_chat_cmd = "agent-cli chat --oneshot"
```

Environment variables are supported for container deployments:

```bash
export AGENT_ID='code'
export NATS_URL='nats://username:password@server_host:server_port'
export AGENT_CHAT_CMD='agent-cli chat --oneshot'
export AGENTBUS_LOG_DIR='~/.agentbus/logs'
export AGENTBUS_LOG_MAX_BYTES=104857600
export AGENTBUS_LOG_BACKUP_COUNT=5
export AGENT_TASK_TIMEOUT_SECONDS=1800
agentbus-worker
```

Precedence:

```text
CLI args > environment variables > TOML config > built-in defaults
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

The log directory is created automatically. Override it with `log_dir`, `log_max_bytes`, and `log_backup_count` in TOML; `AGENTBUS_LOG_DIR`, `AGENTBUS_LOG_MAX_BYTES`, and `AGENTBUS_LOG_BACKUP_COUNT`; or `--log-dir`, `--log-max-bytes`, and `--log-backup-count`.

## Set up NATS streams

After the NATS server is running:

```bash
export NATS_URL='nats://username:password@server_host:server_port'
./scripts/stream-setup.sh
```

This creates:

```text
AGENT_TASKS
AGENT_RESULTS
```

## Publish a test task

```bash
export NATS_URL='nats://username:password@server_host:server_port'
./scripts/publish-task.sh code ping '{"text":"hello"}'
```

Subscribe to results:

```bash
nats --server "$NATS_URL" sub agent.main.results
```

## Ack behavior

```text
valid task + command succeeds and result is published      → ack
valid task + command exits non-zero and result is published → ack
invalid JSON / invalid task schema                         → term if available, otherwise ack
worker crashes before result publish                       → nak if available, then raise
```

## Security notes

- Use one NATS user per agent.
- Restrict each user to only the subjects it needs.
- Use TLS for public NATS deployments.
- Store config files with `chmod 600` if credentials are embedded in `nats_url`.
- Do not put tokens or cookies in task payloads unless strictly necessary.
