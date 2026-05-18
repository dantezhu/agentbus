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
configured agent command via agent_chat_cmd
  ↓
result message published back to NATS
```

## Required local tools

- `nats` CLI configured or installed;
- access to a valid `NATS_URL`;
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
export NATS_URL='tls://username:password@agentbus.example.com:7422'
agentbus task publish code ping '{"text":"hello"}'
```

Equivalent direct publish:

```bash
nats --server "$NATS_URL" pub agent.code.tasks '{
  "id":"task-001",
  "from":"agent-main",
  "to":"agent-code",
  "type":"task.request",
  "task":"ping",
  "payload":{"text":"hello"},
  "reply_to":"agent.main.results",
  "risk_level":"normal",
  "max_hops":3
}'
```

## Watch results

```bash
nats --server "$NATS_URL" sub agent.main.results
```

## Worker config

Default user config path:

```text
~/.agentbus/config.toml
```

```toml
[worker]
agent_id = "code"
nats_url = "tls://username:password@agentbus.example.com:7422"
agent_chat_cmd = ["agent-cli", "chat", "--oneshot"]
stream = "AGENT_TASKS"
durable = "agent-code"
task_subject = "agent.code.tasks"
default_result_subject = "agent.main.results"
timeout_seconds = 1800
log_dir = "~/.agentbus/logs"
log_max_bytes = 104857600
log_backup_count = 5
```

`agent_chat_cmd` is required and should point to the one-shot chat/task command of the target agent program.

## Safety rule

When a task may cause irreversible side effects, external sends, production changes, credential exposure, or cost, the worker prompt instructs the called agent to return `needs_approval` instead of executing directly.

## Troubleshooting

1. Confirm the task subject matches the worker's `agent_id` / `task_subject`.
2. Confirm the worker can connect to `NATS_URL`.
3. Confirm NATS user permissions allow subscribe on `agent.<id>.tasks` and publish on result subjects.
4. Confirm `agent_chat_cmd` works locally before starting the worker.
5. Check worker logs at `~/.agentbus/logs/agentbus-worker.log` for invalid JSON, command timeout, or publish failures.
