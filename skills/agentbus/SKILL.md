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
shared NATS JetStream server
  ↓
agentbus task publish sends task messages
  ↓
target worker consumes agentbus.<agent_id>.tasks
  ↓
worker publishes task.result records
```

## Local setup

Install the AgentBus CLI if it is missing:

```bash
pip install agentbus
```

Expose the shared server URL in the active agent environment:

```bash
AGENTBUS_SERVER_URL='nats://username:password@agentbus.example.com:7422'
```

For Hermes, put the same `AGENTBUS_SERVER_URL=...` line in `~/.hermes/.env`.

## Subject convention

Agent IDs are used literally in subjects.

```text
agentbus.<agent_id>.tasks
agentbus.<agent_id>.results
agentbus.main.results
agentbus.<agent_id>.heartbeat
```

## Publish a task

```bash
agentbus task publish \
  --server-url "$AGENTBUS_SERVER_URL" \
  --to coder \
  --to reviewer \
  --from main \
  --reply-to main \
  'hello'
```

| Argument | Required | Meaning |
| --- | --- | --- |
| `--server-url` | yes | Shared server URL, usually `"$AGENTBUS_SERVER_URL"`. |
| `--to` | yes | Target agent id. Repeat it to publish the same content to multiple agents; AgentBus publishes one task message per target. |
| `content` | yes | Final positional argument. Stored as a plain string at `payload.content`; pass JSON-like data as text and let the receiving agent interpret it. |
| `--from` | no, defaults to `main` | Sender agent id. |
| `--reply-to` | no, defaults to `--from` | Agent id whose result inbox receives the worker execution record. AgentBus derives `agentbus.<reply_to>.results`. |
| `--task-type` | no, defaults to `default` | Optional work classification. |

JSON-like text example:

```bash
agentbus task publish \
  --server-url "$AGENTBUS_SERVER_URL" \
  --to coder \
  --task-type batch \
  '[{"url":"https://example.com"}]'
```

## Read or watch results

```bash
agentbus result get \
  --server-url "$AGENTBUS_SERVER_URL" \
  --agent main
```

`--limit` means read the latest N stored results first. The meaning is the same with and without `--watch`.

Results are worker-generated execution records, not the primary agent-to-agent reply channel. Business replies should be sent as new tasks. Each result embeds the original task whole under `task` for traceability. Top-level duplicate fields such as `request_id`, `from`, `to`, `worker`, and `reply_to` are intentionally omitted.

```bash
agentbus result get \
  --server-url "$AGENTBUS_SERVER_URL" \
  --agent main \
  --limit 20 \
  --watch
```

## Safety rule

When a task may cause irreversible side effects, external sends, production changes, credential exposure, or cost, the worker prompt instructs the called agent to return `needs_approval` instead of executing directly.

## Troubleshooting

1. Confirm `AGENTBUS_SERVER_URL` is set in the active agent environment.
2. Confirm the target id maps to `agentbus.<id>.tasks` and matches `agentbus task publish --to <id>`.
3. Confirm the target worker is running and its `[agent].id` matches the target id.
4. Confirm result reading uses the expected inbox; `--agent main` reads `agentbus.main.results`.
5. If no result arrives, inspect the target worker logs for invalid JSON, command timeout, or publish failures.
