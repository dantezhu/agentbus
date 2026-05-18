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
- inspect results from `agent.main.results` or `agent.<id>.results`;
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

For public deployments, prefer a domain and TLS URL such as `tls://username:password@agentbus.example.com:7422`. The example port is `7422` to avoid the default NATS client port `4222`.

## Subject convention

```text
agent.<agent_id>.tasks
agent.<agent_id>.results
agent.main.results
agent.<agent_id>.heartbeat
```

## Send a task

```bash
agentbus task publish \
  --nats-url 'tls://username:password@agentbus.example.com:7422' \
  --to-agent code \
  --to-agent doc \
  --task ping \
  'hello'
```

Repeat `--to-agent` to send the same content to multiple agents. AgentBus publishes one task message per target agent.

Equivalent direct publish:

```bash
nats --server 'tls://username:password@agentbus.example.com:7422' pub agent.code.tasks '{
  "id":"task-001",
  "from":"agent-main",
  "to":"agent-code",
  "type":"task.request",
  "task":"ping",
  "payload":{"content":"hello"},
  "reply_to":"agent.main.results",
  "risk_level":"normal",
  "max_hops":3
}'
```

## Watch results

```bash
nats --server 'tls://username:password@agentbus.example.com:7422' sub agent.main.results
```

## Worker config

Default user config path:

```text
~/.agentbus/config.toml
```

```toml
[agent]
id = "code"
chat_cmd = ["agent-cli", "chat", "--oneshot", "{input}"]

[worker]
task_timeout_seconds = 1800
max_task_bytes = 1048576
reconnect_time_wait_seconds = 2
max_reconnect_attempts = -1

[nats]
url = "tls://username:password@agentbus.example.com:7422"
stream = "AGENT_TASKS"
task_subject = "agent.code.tasks"
default_result_subject = "agent.main.results"
# Stable JetStream durable consumer name for this worker identity.
durable = "agent-code"

[log]
dir = "~/.agentbus/logs"
max_bytes = 104857600
backup_count = 5
```

`chat_cmd` is required and must include the literal `{input}` placeholder where AgentBus should insert the generated prompt. Prefer list form when the prompt belongs between flags, for example `chat_cmd = ["agent-cli", "run", "--prompt", "{input}", "--json"]`. For Hermes workers, use `chat_cmd = ["hermes", "chat", "-q", "-Q", "{input}"]`. `durable` is the stable NATS JetStream consumer name used to remember worker delivery progress across restarts.

## Safety rule

When a task may cause irreversible side effects, external sends, production changes, credential exposure, or cost, the worker prompt instructs the called agent to return `needs_approval` instead of executing directly.

## Troubleshooting

1. Confirm the task subject matches the worker's `agent_id` / `task_subject`.
2. Confirm the worker can connect to `[nats].url`.
3. Confirm NATS user permissions allow subscribe on `agent.<id>.tasks` and publish on result subjects.
4. Confirm TOML `chat_cmd` works locally before starting the worker.
5. Check worker logs at `~/.agentbus/logs/agentbus-worker.log` for invalid JSON, command timeout, or publish failures.
