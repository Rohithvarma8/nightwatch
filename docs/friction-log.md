# Friction log

Log entries **as they happen**, with exact commands and error text. Submit only entries you actually hit and reproduced. The seeded hypotheses below are things to watch for, not facts. Delete any you don't confirm.

Severity: **Blocker** (couldn't proceed) · **Major** (≥ 1 h lost / ugly workaround) · **Minor** (annoyance) · **Doc** (docs wrong/missing).

---

### FL-001: <short title>
- **Product / tool:** Alexa+ MCP Toolkit · alexa-ai CLI vX · web simulator · Local Inspector · MCP Python SDK vX · AWS <service>
- **Task attempted:**
- **Steps taken:**
  1. `command …`
  2.
- **Expected:**
- **Actual:** (paste error / observed payload)
- **Severity:**
- **Time lost:**
- **Workaround:**
- **Actionable suggestion:** (specific: "Add X to page Y", "CLI should print Z", "Support W")
- **Evidence:** log excerpt / screenshot / commit link

---

## Watch list (hypotheses to confirm or discard)
- [ ] Docs say Builders support spec 2025-11-25, but the Alexa+ client `initialize` sends `protocolVersion: "2025-03-26"` (shown on the Client Lifecycle page). Record what you actually observe.
- [ ] The "401 without `WWW-Authenticate`" requirement conflicts with the MCP auth spec / RFC 9728 guidance and with SDK/API Gateway defaults that add the header.
- [ ] Cognito publishes OIDC discovery, not RFC 8414 `/.well-known/oauth-authorization-server`, and OIDC is listed as unsupported, so a self-hosted metadata doc is needed.
- [ ] Tools refresh only on `alexa-ai deploy`, with no warning when the server's `tools/list` has drifted.
- [ ] Auth metadata cached at deploy time: changing auth settings silently has no effect until redeploy.
- [ ] Manifest needs 6 icon sizes + a 600×900 carousel image just to deploy to the dev stage.
- [ ] The Quickstart's "MCP Apps standard" link points to the transports section of the spec, not the Apps extension.
- [ ] Web simulator: what's visible in "response details" (tool calls? latency? raw payloads?) and what's missing for debugging.
- [ ] Local Inspector requires Node 24+ and Playwright for visual mode.
- [ ] MCP Python SDK v1 → v2 API changes (FastMCP → MCPServer; transport options moved), with many tutorials still showing v1.
