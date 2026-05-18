#!/usr/bin/env bash
set -euo pipefail

: "${NATS_URL:?Set NATS_URL, e.g. tls://username:password@agentbus.example.com:7422}"

TARGET_AGENT="${1:?Usage: publish-task.sh <target-agent> <task-name> [payload-json]}"
TASK_NAME="${2:?Usage: publish-task.sh <target-agent> <task-name> [payload-json]}"
PAYLOAD_JSON="${3:-{}}"
FROM_AGENT="${FROM_AGENT:-agent-main}"
REPLY_TO="${REPLY_TO:-agent.main.results}"
TASK_ID="${TASK_ID:-task-$(date -u +%Y%m%dT%H%M%SZ)-$RANDOM}"
SUBJECT="agent.${TARGET_AGENT}.tasks"

python3 - "$TASK_ID" "$FROM_AGENT" "agent-${TARGET_AGENT}" "$TASK_NAME" "$REPLY_TO" "$PAYLOAD_JSON" <<'PY' | nats --server "$NATS_URL" pub "$SUBJECT"
import json
import sys

task_id, from_agent, to_agent, task_name, reply_to, payload_raw = sys.argv[1:]
payload = json.loads(payload_raw)
message = {
    "id": task_id,
    "from": from_agent,
    "to": to_agent,
    "type": "task.request",
    "task": task_name,
    "payload": payload,
    "reply_to": reply_to,
    "risk_level": "normal",
    "max_hops": 3,
}
print(json.dumps(message, ensure_ascii=False, separators=(",", ":")))
PY
