#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8765}"
HOST="${HOST:-127.0.0.1}"
BASE_URL="${BASE_URL:-http://${HOST}:${PORT}}"
TASK="${TASK:-Open https://example.com and return the H1 text}"
TIMEOUT="${TIMEOUT:-180}"
POLL_INTERVAL="${POLL_INTERVAL:-2}"
SERVER_BOOT_TIMEOUT="${SERVER_BOOT_TIMEOUT:-30}"
SERVER_LOG="${SERVER_LOG:-/tmp/task2-smoke-api.log}"
export LLM_DISABLE_THINKING="${LLM_DISABLE_THINKING:-1}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

server_pid=""
cleanup() {
  if [ -n "$server_pid" ] && kill -0 "$server_pid" 2>/dev/null; then
    echo "[smoke] stopping server (pid $server_pid)"
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT

if curl -fsS "$BASE_URL/" -o /dev/null 2>/dev/null; then
  echo "[smoke] reusing existing server at $BASE_URL"
else
  echo "[smoke] starting server: uv run uvicorn api.server:app --host $HOST --port $PORT"
  ( cd "$SCRIPT_DIR" && uv run uvicorn api.server:app --host "$HOST" --port "$PORT" ) \
    > "$SERVER_LOG" 2>&1 &
  server_pid=$!
  echo "[smoke] server pid: $server_pid (log: $SERVER_LOG)"

  boot_deadline=$(( $(date +%s) + SERVER_BOOT_TIMEOUT ))
  until curl -fsS "$BASE_URL/" -o /dev/null 2>/dev/null; do
    if ! kill -0 "$server_pid" 2>/dev/null; then
      echo "[smoke] FAIL: server exited during boot. log:" >&2
      tail -50 "$SERVER_LOG" >&2 || true
      exit 1
    fi
    if [ "$(date +%s)" -ge "$boot_deadline" ]; then
      echo "[smoke] FAIL: server did not become ready within ${SERVER_BOOT_TIMEOUT}s" >&2
      tail -50 "$SERVER_LOG" >&2 || true
      exit 1
    fi
    sleep 1
  done
  echo "[smoke] server ready at $BASE_URL"
  sleep "${SERVER_WARMUP:-3}"
fi

echo "[smoke] target: $BASE_URL"
echo "[smoke] task:   $TASK"

echo "[smoke] POST /tasks"
payload_body=$(TASK="$TASK" python3 -c 'import json,os; print(json.dumps({"task": os.environ["TASK"]}))')
create_response=$(
  curl -fsS -X POST "$BASE_URL/tasks" \
    -H "Content-Type: application/json" \
    -d "$payload_body"
)
run_id=$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["id"])' <<<"$create_response")
echo "[smoke] run_id: $run_id"

deadline=$(( $(date +%s) + TIMEOUT ))
status="running"
payload="{}"
while [ "$(date +%s)" -lt "$deadline" ]; do
  payload=$(curl -fsS "$BASE_URL/tasks/$run_id")
  status=$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read()).get("status","running"))' <<<"$payload")
  echo "[smoke] status: $status"
  if [ "$status" != "running" ]; then
    break
  fi
  sleep "$POLL_INTERVAL"
done

if [ "$status" = "running" ]; then
  echo "[smoke] FAIL: task still running after ${TIMEOUT}s" >&2
  exit 1
fi

echo "[smoke] final payload:"
python3 -c 'import json,sys; print(json.dumps(json.loads(sys.stdin.read()), indent=2))' <<<"$payload"

echo "[smoke] GET /tasks/$run_id/trace"
trace_lines=$(curl -fsS "$BASE_URL/tasks/$run_id/trace" | wc -l)
echo "[smoke] trace events: $trace_lines"
if [ "$trace_lines" -lt 1 ]; then
  echo "[smoke] WARN: trace is empty (event wiring lands in ticket #20)" >&2
fi

case "$status" in
  succeeded|unverified)
    echo "[smoke] PASS: status=$status"
    exit 0
    ;;
  *)
    echo "[smoke] FAIL: status=$status" >&2
    exit 1
    ;;
esac
