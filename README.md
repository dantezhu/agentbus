# agentbus

`agentbus` is a small NATS JetStream based task bus for distributed agent programs.

It is designed for this architecture:

```text
coordinator agent / human entry point
  ↓ publishes task
public NATS JetStream server
  ↓ durable delivery
agentbus-worker long-running process on each worker machine
  ↓ invokes configured agent command
worker publishes result message and ack/nak/term the task
```

## Design goals

- No bot-to-bot chat dependency.
- No direct inbound access needed for worker machines.
- Generic agent command integration through `agent_chat_cmd`.
- Worker configuration via TOML file, with env/CLI overrides.
- NATS subjects keep routing explicit and permissionable.
- Durable task delivery through JetStream, not plain fire-and-forget pub/sub.

## Requirements

Server side:

- `nats-server` with JetStream enabled.
- `nats` CLI for stream setup and debugging.
- A reachable TCP port for NATS clients, usually `4222`.

Worker side:

- Python >= 3.11.
- Network access from the worker machine to the NATS server.
- A one-shot agent command configured as `agent_chat_cmd`.

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

## 1. Configure the NATS server

Copy the sample config to your server:

```bash
sudo mkdir -p /etc/nats /data/jetstream
sudo cp config/nats-server.conf /etc/nats/agentbus.conf
sudo chmod 600 /etc/nats/agentbus.conf
sudo chown -R nats:nats /data/jetstream 2>/dev/null || true
```

Edit the config before starting the server:

```bash
sudo $EDITOR /etc/nats/agentbus.conf
```

At minimum, change these values:

```text
agent-main password
agent-code password
agent-doc password
jetstream.store_dir, if /data/jetstream is not appropriate
```

The sample config defines three users:

```text
agent-main   publishes tasks and subscribes to central results
agent-code   subscribes to agent.code.tasks and publishes results
agent-doc    subscribes to agent.doc.tasks and publishes results
```

It also enables JetStream:

```text
jetstream {
  store_dir: "/data/jetstream"
  max_mem_store: 256MiB
  max_file_store: 10GiB
}
```

Start the server with the config:

```bash
nats-server -c /etc/nats/agentbus.conf
```

For a real deployment, run this under your service manager, for example systemd, Docker, or a managed NATS service.

Important network notes:

- Expose the NATS client port, usually `4222`, only to machines that need to connect.
- Keep the monitoring port `8222` private or bind it only to localhost/VPN.
- Use TLS for public internet deployments. If TLS is enabled, clients should use a `tls://...` NATS URL or equivalent TLS client options.

The sample config includes a commented TLS block:

```text
# tls {
#   cert_file: "/etc/nats/tls/fullchain.pem"
#   key_file: "/etc/nats/tls/privkey.pem"
# }
```

## 2. Create JetStream streams

After the NATS server is running, create the task and result streams.

Use a user with JetStream API permission. In the sample config, `agent-main` has `$JS.API.>` access:

```bash
export NATS_URL='nats://agent-main:agent_main_password@server_host:4222'
./scripts/stream-setup.sh
```

This creates:

```text
AGENT_TASKS     subjects: agent.*.tasks    max age: 7d
AGENT_RESULTS   subjects: agent.*.results  max age: 30d
```

You can inspect the streams with:

```bash
nats --server "$NATS_URL" stream ls
nats --server "$NATS_URL" stream info AGENT_TASKS
nats --server "$NATS_URL" stream info AGENT_RESULTS
```

## 3. Install the worker

Use a standard `venv` + `pip` setup on each worker machine:

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

## 4. Configure the worker

Prefer a config file:

```bash
mkdir -p ~/.agentbus
cp config/agentbus.worker.example.toml ~/.agentbus/config.toml
$EDITOR ~/.agentbus/config.toml
chmod 600 ~/.agentbus/config.toml
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
nats_url = "nats://agent-code:agent_code_password@server_host:4222"
agent_chat_cmd = ["agent-cli", "chat", "--oneshot"]
log_dir = "~/.agentbus/logs"
log_max_bytes = 104857600
log_backup_count = 5
```

A fuller example:

```toml
[worker]
agent_id = "code"
nats_url = "nats://agent-code:agent_code_password@server_host:4222"
stream = "AGENT_TASKS"
durable = "agent-code"
task_subject = "agent.code.tasks"
default_result_subject = "agent.main.results"
agent_chat_cmd = ["agent-cli", "chat", "--oneshot"]
timeout_seconds = 1800
log_dir = "~/.agentbus/logs"
log_max_bytes = 104857600
log_backup_count = 5
```

`agent_chat_cmd` can also be a string:

```toml
agent_chat_cmd = "agent-cli chat --oneshot"
```

Environment variables are supported for container deployments:

```bash
export AGENT_ID='code'
export NATS_URL='nats://agent-code:agent_code_password@server_host:4222'
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

## 5. Run the worker

Foreground mode:

```bash
agentbus-worker --config ~/.agentbus/config.toml
```

For long-running deployment, use one of the included templates:

```text
deploy/systemd/agentbus-worker.service
deploy/launchd/com.agentbus.worker.plist
```

Before installing a service, edit the template paths, user, working directory, and config path for the target machine.

## 6. Publish a test task

Start a result subscriber in one terminal:

```bash
export NATS_URL='nats://agent-main:agent_main_password@server_host:4222'
nats --server "$NATS_URL" sub agent.main.results
```

Publish a test task in another terminal:

```bash
export NATS_URL='nats://agent-main:agent_main_password@server_host:4222'
./scripts/publish-task.sh code ping '{"text":"hello"}'
```

The `code` argument maps to this task subject:

```text
agent.code.tasks
```

If the `code` worker is running, the subscriber should receive a `task.result` message on:

```text
agent.main.results
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

The log directory is created automatically. Override it with `log_dir`, `log_max_bytes`, and `log_backup_count` in TOML; `AGENTBUS_LOG_DIR`, `AGENTBUS_LOG_MAX_BYTES`, and `AGENTBUS_LOG_BACKUP_COUNT`; or `--log-dir`, `--log-max-bytes`, and `--log-backup-count`.

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
- Restrict each user to only the subjects it needs.
- Use TLS for public NATS deployments.
- Keep monitoring/admin ports private.
- Store config files with `chmod 600` if credentials are embedded in `nats_url`.
- Do not put tokens, cookies, or authorization headers in task payloads unless strictly necessary.
- Treat tasks that delete data, send external messages, deploy code, merge PRs, or spend money as approval-required.

## License

Apache License 2.0. See [LICENSE](LICENSE).
