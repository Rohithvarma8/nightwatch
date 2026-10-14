# Friction log

Log entries **as they happen**, with exact commands and error text. Submit only entries you actually hit and reproduced. The seeded hypotheses below are things to watch for, not facts. Delete any you don't confirm.

Severity: **Blocker** (couldn't proceed) · **Major** (≥ 1 h lost / ugly workaround) · **Minor** (annoyance) · **Doc** (docs wrong/missing).

---

### FL-001: No self-serve path to Alexa+ add-on developer access for hackathon participants

- **Product / tool:** Alexa+ Developer Console · Alexa AI CLI onboarding (Set Up Your Development Environment) · DevAssistant
- **Date:** 2026-10-13
- **Task attempted:** Get access to the Alexa+ MCP Toolkit (console, `alexa-ai` CLI, web simulator) to onboard a self-hosted MCP server for the Alexa+ track.
- **Steps taken:**
  1. Followed "Set Up Your Development Environment": created IAM user `alexa-ai-tools` with the documented inline policy allowing `sts:AssumeRole` on `arn:aws:iam::372468808636:role/AddOn3PDeveloperToolsRead`; configured `alexa-ai-user` and `alexa-ai` profiles exactly as documented.
  2. Ran `aws sts get-caller-identity --profile alexa-ai-user` → success (my account, my IAM user).
  3. Ran `aws sts get-caller-identity --profile alexa-ai` →
     `AccessDenied ... User: arn:aws:iam::946509368103:user/alexa-ai-tools is not authorized to perform: sts:AssumeRole on resource: arn:aws:iam::372468808636:role/AddOn3PDeveloperToolsRead`
  4. Completed Amazon Developer account registration, then opened developer.amazon.com dashboard → "Alexa+ Developer Console" → page shows only "Coming Soon".
  5. Opened DevAssistant (Alexa+), described both issues. It confirmed the AWS account must be provided to an Alexa Solutions Architect and allowlisted Amazon-side; "not something that can be self-served." Filed support case **96298466**.
- **Expected:** As a registered hackathon participant, a documented way to get console + CLI access (a form, Devpost instructions, or automatic enablement for registered participants).
- **Actual:** Docs assume an existing relationship with an Alexa Solutions Architect ("the AWS account that you provided to the Alexa Solutions Architect"). The console shows "Coming Soon" with no explanation or request link. The only route is a support case (typical response time: 2 business days) with a ~10-day hackathon window.
- **Severity:** Blocker
- **Time lost:** ~2 hours
- **Workaround:** Filed case 96298466. Continued building and testing the MCP server against MCP Inspector, to the published Alexa+ requirements, so onboarding is quick once access is granted. Fallback: the simulated Alexa+ path allowed by the hackathon rules.
- **Actionable suggestions:**
  1. Replace the bare "Coming Soon" page with the reason and a "Request access" button that captures the developer account + AWS account ID.
  2. In "Set Up Your Development Environment," state up front that the AWS account must be allowlisted, how to request it, and the expected turnaround, before the IAM steps.
  3. For hackathons, auto-enable registered participants (or publish a dedicated access form on the Devpost Resources page).
  4. Have the CLI or docs detect this AccessDenied and print "Your AWS account isn't onboarded yet; request access at <link>" instead of a raw STS error.
- **Evidence:** screenshots of "Coming Soon" page and DevAssistant conversation; terminal output above; case ID 96298466.

---

### FL-002: Support entry point and message limits are hard to discover

- **Product / tool:** DevAssistant / Get Support from Amazon docs
- **Date:** 2026-10-13
- **Task attempted:** Contact Alexa+ support about the access block.
- **Steps taken:** Looked for a support form; found via the "Get Support from Amazon" doc page that the channel is DevAssistant (full-screen at developer.amazon.com/alexa/console/contact-us). Pasted a detailed report.
- **Expected:** A form or chat that accepts a full error report (ARN, error text, account IDs).
- **Actual:** The message box is limited to 500 characters, so the report had to be cut down and split across messages. The DevAssistant entry point isn't linked from the "Coming Soon" console page.
- **Severity:** Minor
- **Time lost:** ~15 minutes
- **Workaround:** Condensed the report; sent extra details as follow-up messages.
- **Actionable suggestion:** Raise the limit (or allow attachments) for case-filing flows; link DevAssistant directly from the "Coming Soon" console page.
- **Evidence:** DevAssistant conversation.

### FL-003: Stateless + JSON-response Streamable HTTP app still holds GET /mcp open as an SSE stream

- **Product / tool:** MCP Python SDK `mcp==2.3.0`, `MCPServer.streamable_http_app(stateless_http=True, json_response=True)`
- **Date:** 2026-10-13
- **Task attempted:** Serve a stateless, JSON-only MCP endpoint where GET `/mcp` returns 405 (no standalone SSE stream), as Night Watch requires for Alexa+.
- **Steps taken:** Built the app with `stateless_http=True, json_response=True`, ran its lifespan, and sent `GET /mcp` with `Accept: text/event-stream` over an in-process ASGI client.
- **Expected:** 405 Method Not Allowed. The spec allows a server to refuse the GET stream, and with JSON responses and no sessions there is nothing to push on it.
- **Actual:** The request stayed open (an SSE stream) until my 2 s client timeout cancelled it. No 405.
- **Severity:** Minor
- **Time lost:** ~15 minutes
- **Workaround:** A small ASGI wrapper (`RejectGetStream` in `server/src/nightwatch/app.py`) returns 405 with `Allow: POST` for GET `/mcp` before the request reaches the SDK. Covered by `test_get_mcp_is_405`.
- **Actionable suggestion:** In stateless mode (at least combined with `json_response=True`), answer GET with 405, or add an option such as `allow_get_stream=False`.
- **Evidence:** Probe script output: `bare SDK GET /mcp -> hung (SSE stream held open)`. Unsure whether this is intentional (stateless servers may still emit server-initiated messages); reporting the behavior as observed.

---

### FL-004: SDK client can't choose the protocolVersion it offers in `initialize`

- **Product / tool:** MCP Python SDK `mcp==2.3.0`, `mcp.Client` / `ClientSession.initialize`
- **Date:** 2026-10-13
- **Task attempted:** A contract test that initializes with `protocolVersion: "2025-03-26"` (what the Alexa+ client is documented to send) using the SDK client, per our testing plan.
- **Steps taken:** Read `Client` and `ClientSession.initialize`. `mode=` takes `"legacy"`, `"auto"`, or a *modern* version string only. `initialize()` always sends `LATEST_HANDSHAKE_VERSION` (`2025-11-25`).
- **Expected:** A way to pin the handshake version (e.g. `Client(..., mode="legacy", protocol_version="2025-03-26")`) to test older-client compatibility.
- **Actual:** No public parameter for it.
- **Severity:** Minor
- **Time lost:** ~10 minutes
- **Workaround:** The test monkeypatches `mcp.client.session.LATEST_HANDSHAKE_VERSION`. A second test sends the raw JSON-RPC `initialize` with httpx to check the exact wire behavior.
- **Actionable suggestion:** Expose a handshake `protocol_version` option on `Client`/`ClientSession`.
- **Evidence:** `ClientSession.initialize` in `mcp/client/session.py` hard-codes `protocol_version=LATEST_HANDSHAKE_VERSION`.

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
- [ ] SDK auto-enables DNS-rebinding protection (allowed hosts = localhost only) when `streamable_http_app(host=...)` is left at its default `127.0.0.1`. Behind API Gateway + Lambda Web Adapter, the `Host` header will be the execute-api domain. Check on Day 2 whether requests get rejected.
- [ ] MCP Python SDK v1 → v2 API changes (FastMCP → MCPServer; transport options moved), with many tutorials still showing v1.
