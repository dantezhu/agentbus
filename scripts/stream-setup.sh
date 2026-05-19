#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <nats-url>" >&2
  echo "Example: $0 tls://username:password@agentbus.example.com:7422" >&2
  exit 2
fi

nats_url="$1"

nats --server "$nats_url" stream add AGENT_TASKS \
  --subjects 'agentbus.*.tasks' \
  --storage file \
  --retention limits \
  --discard old \
  --max-age 7d \
  --ack \
  --defaults

nats --server "$nats_url" stream add AGENT_RESULTS \
  --subjects 'agentbus.*.results' \
  --storage file \
  --retention limits \
  --discard old \
  --max-age 30d \
  --defaults
