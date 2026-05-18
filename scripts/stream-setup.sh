#!/usr/bin/env bash
set -euo pipefail

: "${NATS_URL:?Set NATS_URL, e.g. tls://username:password@agentbus.example.com:7422}"

nats --server "$NATS_URL" stream add AGENT_TASKS \
  --subjects 'agent.*.tasks' \
  --storage file \
  --retention limits \
  --discard old \
  --max-age 7d \
  --ack \
  --defaults

nats --server "$NATS_URL" stream add AGENT_RESULTS \
  --subjects 'agent.*.results' \
  --storage file \
  --retention limits \
  --discard old \
  --max-age 30d \
  --defaults
