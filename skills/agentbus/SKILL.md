---
name: agentbus
description: Use when distributed agent programs need to send tasks to each other through AgentBus/NATS, inspect task results, or troubleshoot the shared agent message bus.
version: 0.1.0
author: AgentBus
license: Apache-2.0
platforms: [linux, macos]
metadata:
  tags: [agents, nats, jetstream, messaging]
---

# AgentBus

## When to use

Use this skill when an agent needs to:

- send an asynchronous task to another agent;
- inspect results from `agentbus.main.results` or `agentbus.<id>.results`;
- troubleshoot NATS/JetStream routing for AgentBus.

## Core model

```text
public NATS JetStream server
  ↓
agentbus worker run on each worker machine
  ↓
configured agent command via TOML chat_cmd
  ↓
result message published back to NATS
```

## Required local tools

- `nats` CLI configured or installed;
- a private AgentBus TOML config containing `[nats].url`;
- `agentbus` installed on worker machines.

Examples use the normal NATS URL form such as `nats://username:password@agentbus.example.com:7422`. For public deployments, prefer enabling TLS on the server and switching client URLs to `tls://...`. The example port is `7422` to avoid the default NATS client port `4222`.

## Subject convention

Agent IDs are used literally in subjects. AgentBus does not strip or add prefixes such as `agent-`.

```text
agentbus.<agent_id>.tasks
agentbus.<agent_id>.results
agentbus.main.results
agentbus.<agent_id>.heartbeat
```

## Send a task

```bash
agentbus task publish \
  --nats-url 'nats://username:password@agentbus.example.com:7422' \
  --to coder \
  --to reviewer \
  --from main \
  --reply-to main \
  --task-type ping \
  'hello'
```

Repeat `--to` to send the same content to multiple agents. AgentBus publishes one task message per target agent. `--reply-to` is an agent id, like `--from` and `--to`; it controls which agent result inbox receives the worker execution record. When omitted, it defaults to `--from`, and AgentBus derives the result subject internally as `agentbus.<reply_to>.results`.
The positional content is stored as a plain string at `payload.content`. If you need JSON-like content, pass it as text and let the receiving agent interpret it.

JSON-like text example:

```bash
agentbus task publish \
  --nats-url 'nats://username:password@agentbus.example.com:7422' \
  --to coder \
  --task-type batch \
  '[{"url":"https://example.com"}]'
```

Equivalent direct publish:

```bash
nats --server 'nats://username:password@agentbus.example.com:7422' pub agentbus.coder.tasks '{
  "id":"task-001",
  "from":"main",
  "to":"coder",
  "reply_to":"main",
  "type":"task.request",
  "task_type":"ping",
  "payload":{"content":"hello"}
}'
```

## Read or watch results

```bash
agentbus result get \
  --nats-url 'nats://username:password@agentbus.example.com:7422' \
  --agent main
```

`--limit` means read the latest N stored results first. The meaning is the same with and without `--watch`.

Results are worker-generated execution records, not the primary agent-to-agent reply channel. Business replies should be sent as new tasks. Each result embeds the original task whole under `task` for traceability. Top-level duplicate fields such as `request_id`, `from`, `to`, `worker`, and `reply_to` are intentionally omitted.

```bash
agentbus result get \
  --nats-url 'nats://username:password@agentbus.example.com:7422' \
  --agent main \
  --limit 20 \
  --watch
```

## Worker config

Default user config path:

```text
~/.agentbus/config.toml
```

```toml
[agent]
id = "coder"
chat_cmd = ["agent-cli", "chat", "--oneshot", "{input}"]

[worker]
task_timeout_seconds = 1800
max_task_bytes = 1048576
reconnect_time_wait_seconds = 2
max_reconnect_attempts = -1

[nats]
url = "nats://username:password@agentbus.example.com:7422"
stream = "AGENT_TASKS"
task_subject = "agentbus.coder.tasks"
default_result_subject = "agentbus.main.results"
# Stable JetStream durable consumer name for this worker identity.
durable = "coder"

[log]
dir = "~/.agentbus/logs"
max_bytes = 104857600
backup_count = 5
```

`chat_cmd` is required, must be a TOML array of strings, and must include the literal `{input}` placeholder where AgentBus should insert the generated prompt. String-form commands are rejected so the prompt is always passed as one explicit argv argument, never shell-parsed. For prompts between flags, use `chat_cmd = ["agent-cli", "run", "--prompt", "{input}", "--json"]`. For Hermes workers, use `chat_cmd = ["hermes", "chat", "-q", "-Q", "{input}"]`. `durable` is the stable NATS JetStream consumer name used to remember worker delivery progress across restarts.

## Safety rule

When a task may cause irreversible side effects, external sends, production changes, credential exposure, or cost, the worker prompt instructs the called agent to return `needs_approval` instead of executing directly.

## Troubleshooting

1. Confirm the task subject matches the worker's `agent_id` / `task_subject`.
2. Confirm the worker can connect to `[nats].url`.
3. Confirm NATS user permissions allow subscribe on `agentbus.<id>.tasks` and publish on result subjects.
4. Confirm TOML `chat_cmd` works locally before starting the worker.
5. Check worker logs at `~/.agentbus/logs/agentbus-worker.log` for invalid JSON, command timeout, or publish failures.
