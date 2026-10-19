#!/usr/bin/env bash
# Post-deploy smoke test (dev). Replays one archived alert through the real path
# (bus → incident builder → triage → DynamoDB → MCP) and fails on any Lambda error.
# Unit tests run against moto, which doesn't enforce IAM; this does.
#   scripts/smoke.sh [alert.json]     (SMOKE_TIMEOUT_S, default 120)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FILE="${1:-$HOME/nightwatch-alert-archive/archive/nws/2026-10-15/b63ffdcd0a37ca41.json}"
TIMEOUT="${SMOKE_TIMEOUT_S:-120}"
AWS=(--profile nightwatch --region us-west-2)
LOG_GROUPS=(/aws/lambda/nightwatch-incident-builder /aws/lambda/nightwatch-triage)
MCP_URL="$(terraform -chdir="$ROOT/infra/envs/dev" output -raw mcp_url)"

logs() {  # logs <group> <since-ms>: messages as JSON lines
  aws logs filter-log-events "${AWS[@]}" --log-group-name "$1" --start-time "$2" \
    --query 'events[].message' --output json | python3 -c \
    'import json,sys; [print(json.dumps(m)) for m in json.load(sys.stdin)]'
}

T0=$(( $(date +%s) * 1000 ))
echo "smoke: replaying $(basename "$FILE")"
make -s -C "$ROOT" replay FILE="$FILE" | tail -1

deadline=$(( $(date +%s) + TIMEOUT ))
while :; do
  for g in "${LOG_GROUPS[@]}"; do
    errors="$(logs "$g" "$T0" | grep -E '\[ERROR\]|Task timed out|AccessDenied' || true)"
    if [ -n "$errors" ]; then
      echo "FAIL: errors in $g:"; echo "$errors" | cut -c1-400; exit 1
    fi
  done
  done_line="$(logs /aws/lambda/nightwatch-triage "$T0" | grep 'triage done' | tail -1 || true)"
  [ -n "$done_line" ] && break
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "FAIL: no 'triage done' within ${TIMEOUT}s"; exit 1
  fi
  sleep 5
done

echo "$done_line" | python3 -c '
import json, sys
d = json.loads(json.loads(sys.stdin.read()))
s = d["summarizer"]
print(f"triage: saved={d[\"saved\"]} model={s[\"model\"]} fallback_used={s[\"fallback_used\"]} "
      f"grounding_passed={s[\"grounding_passed\"]} template_fields={s.get(\"template_fields\")}")
if s["fallback_used"]:
    print("WARN: template fallback (see attempts in the triage log)")'

OUT="$(mktemp)"
trap 'rm -f "$OUT"' EXIT
code="$(curl -s -o "$OUT" -w '%{http_code}' \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_active_incidents","arguments":{}}}' \
  "$MCP_URL")"
python3 - "$code" "$OUT" <<'PY'
import json, sys
code, path = sys.argv[1], sys.argv[2]
result = json.load(open(path)).get("result", {})
if code != "200" or result.get("isError"):
    sys.exit(f"FAIL: get_active_incidents HTTP {code} isError={result.get('isError')}")
print("mcp:", result["content"][0]["text"])
PY
echo "smoke: OK"
