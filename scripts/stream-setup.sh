#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <server-url>" >&2
  echo "Example: $0 nats://username:password@127.0.0.1:7678" >&2
  exit 2
fi

server_url="$1"

nats --server "$server_url" stream add AGENTBUS_TASKS \
  --subjects 'agentbus.*.tasks' \
  --storage file \
  --retention limits \
  --discard old \
  --max-age 7d \
  --ack \
  --defaults

nats --server "$server_url" stream add AGENTBUS_RESULTS \
  --subjects 'agentbus.*.results' \
  --storage file \
  --retention limits \
  --discard old \
  --max-age 30d \
  --defaults
