#!/usr/bin/env bash
# Print the live get_active_incidents spoken overview and the card's "Do now" per incident.
#   scripts/mcp_overview.sh <mcp_url>
set -euo pipefail
curl -s -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_active_incidents","arguments":{}}}' \
  "${1:?usage: mcp_overview.sh <mcp_url>}" | python3 -c '
import json, sys
r = json.load(sys.stdin)["result"]
print("spoken      " + r["content"][0]["text"])
for i in r["structuredContent"]["incidents"]:
    print("card        %s: Do now = %r; due %s" % (i["title"], i["top_action"], i["escalation_due_at"]))
'
