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

### FL-005: SDK DNS-rebinding protection is silently on with a localhost-only allow list, so every request behind API Gateway gets 421

- **Product / tool:** MCP Python SDK `mcp==2.3.0`, `MCPServer.streamable_http_app()`
- **Date:** 2026-10-14
- **Task attempted:** Serve the stateless MCP app on Lambda (Lambda Web Adapter + uvicorn) behind an API Gateway HTTP API.
- **Steps taken:** Built the app with `streamable_http_app(stateless_http=True, json_response=True)`, which leaves `host` at its default `"127.0.0.1"`. POSTed `initialize` in-process with `Host: abc123.execute-api.us-west-2.amazonaws.com`.
- **Expected:** Either no Host validation (the app isn't binding a socket here, so `host` means nothing to it) or a clear opt-in.
- **Actual:** `421 Misdirected Request`, body `Invalid Host header`, logged as `Invalid Host header: abc123.execute-api.us-west-2.amazonaws.com`. Because `host` defaults to `127.0.0.1`, `streamable_http_app()` auto-enables `TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"])`. Also: `Host: localhost` with no port is rejected, because the `:*` patterns require a port. The parameter is named `host` (it reads like a bind address), and nothing says it controls Host-header validation for an app you mount yourself.
- **Severity:** Minor (caught locally before deploy; would have been Major to debug on Lambda, where it shows up as a 421 from behind API Gateway)
- **Time lost:** ~20 minutes
- **Workaround:** Pass `transport_security=` explicitly: the localhost defaults plus hosts from the `MCP_ALLOWED_HOSTS` env var (comma-separated), with `https://<host>` added to the allowed origins. Terraform sets the var to the execute-api domain. See `transport_security()` in `server/src/nightwatch/app.py`, covered by `tests/contract/test_allowed_hosts.py`.
- **Actionable suggestions:**
  1. Log once at startup when DNS-rebinding protection is auto-enabled, including the allow list.
  2. Document in `streamable_http_app()` that `host` also selects the Host-header policy, and show the deploy-behind-a-proxy setup.
  3. Accept a bare `localhost` (no port) in the default list.
- **Evidence:** In-process probe: `abc123.execute-api.us-west-2.amazonaws.com 421 Invalid Host header`, `localhost 421`, `127.0.0.1:8080 200`. Source: `mcp/server/mcpserver/server.py` (`streamable_http_app`, the auto-enable block) and `mcp/server/transport_security.py`. Likely intentional secure-by-default; the issue is that it's invisible.

---

### FL-006: MCP Python SDK import alone costs ~0.9 s of Lambda cold start; more memory doesn't help

- **Product / tool:** MCP Python SDK `mcp==2.3.0` on AWS Lambda (python3.12, arm64, Lambda Web Adapter v1.1.0)
- **Date:** 2026-10-15
- **Task attempted:** Get the MCP server's cold start under Alexa+'s 500 ms round-trip budget without provisioned concurrency.
- **Steps taken:**
  1. First request after deploy: `curl -w '%{time_total}'` = 1.766 s; REPORT `Init Duration: 1235.39 ms`. The log timeline shows ~1210 ms before uvicorn's `Started server process`; app startup, the `/healthz` readiness check and the request together take ~35 ms.
  2. Forced fresh environments on `$LATEST` (`update-function-configuration`, then `aws lambda invoke --log-type Tail`), 3 runs per memory size. Init Duration: 512 MB = 834 / 1189 / 1146 ms; 1024 MB = 1176 / 1154 / 1171 ms; 1769 MB = 1175 / 1263 / 1136 ms.
  3. Set `PYTHONPROFILEIMPORTTIME=1` on `$LATEST`. Cumulative import times: `mcp.server.mcpserver` 886 ms, of which `mcp_types` 315 ms (`mcp_types._types` 142 ms self, `_v2026_07_28` 127 ms, `_v2025_11_25` 97 ms) and `mcp.client` 340 ms; then `uvicorn` 121 ms. Our own package adds ~2 ms. The same import on an Apple-silicon laptop takes ~245 ms.
- **Expected:** A server-only import of a lightweight MCP server to cost well under 500 ms, and some improvement from more memory/CPU.
- **Actual:** ~1.15 s Init Duration no matter the memory size. `import mcp.server.mcpserver` runs `mcp/__init__.py`, which imports the client (`Client`, `ClientSession`, `stdio_client`, ...) plus the pydantic models for every protocol revision. Most of `mcp.client`'s 340 ms is `mcp.server` modules imported through `mcp.client._memory`, which the server needs anyway, so a lazy client import would save only ~50 ms.
- **Severity:** Major (cold requests break the 500 ms budget; no fix possible in our own code)
- **Time lost:** ~45 minutes
- **Workaround:** None in our code. Options: provisioned concurrency = 1 (always-on cost) or Lambda SnapStart for Python (not yet measured).
- **Actionable suggestions:**
  1. Make `mcp/__init__.py` imports lazy (PEP 562 `__getattr__`) so server-only users don't load the client and stdio stacks.
  2. Load per-revision `mcp_types` modules only when a session negotiates that revision, or build pydantic models lazily (`defer_build`).
  3. Document cold-start numbers for serverless hosting.
- **Evidence:** REPORT lines and the import-time log above (CloudWatch `/aws/lambda/nightwatch-mcp`, 2026-10-15). I'm not certain why memory has no effect on Init Duration; reporting what I measured.

---

### FL-007: Terraform AWS provider deprecation warning points at the wrong `range_key`

- **Product / tool:** Terraform AWS provider `hashicorp/aws` 6.68.0, `aws_dynamodb_table`
- **Date:** 2026-10-15
- **Task attempted:** Define the single table with a GSI the way most examples show: `hash_key` / `range_key` on the table and inside `global_secondary_index`.
- **Steps taken:** `terraform -chdir=infra/envs/dev validate`
- **Expected:** No warning, or a warning that names the nested block.
- **Actual:**
  ```
  Warning: Argument is deprecated
    with module.data.aws_dynamodb_table.this,
    on ../../modules/data/main.tf line 2, in resource "aws_dynamodb_table" "this":
  range_key is deprecated. Use key_schema instead.
  (and one more similar warning elsewhere)
  ```
  The warning points at the resource's first line and says `range_key`, which reads like the table-level `range_key`. But `terraform providers schema -json` shows the table-level `hash_key`/`range_key` are **not** deprecated; only `global_secondary_index.hash_key`/`range_key` are, and the replacement is a `key_schema { attribute_name, key_type }` block **inside the GSI**. There is no table-level `key_schema` block.
- **Severity:** Minor
- **Time lost:** ~10 minutes
- **Workaround:** Inspected `terraform providers schema -json` for `aws_dynamodb_table`, then moved the GSI keys into two `key_schema` blocks (`infra/modules/data/main.tf`). The table keeps `hash_key`/`range_key`.
- **Actionable suggestion:** Point the diagnostic at the nested `global_secondary_index` attribute, and name it in the message ("global_secondary_index.range_key is deprecated; use global_secondary_index.key_schema").
- **Evidence:** validate output above; provider schema dump (`hash_key`/`range_key` deprecated only under `global_secondary_index`). Unsure whether this is Terraform core's diagnostic placement or the provider's; reporting as observed.

---

## Watch list (hypotheses to confirm or discard)
- [ ] Docs say Builders support spec 2025-11-25, but the Alexa+ client `initialize` sends `protocolVersion: "2025-03-26"` (shown on the Client Lifecycle page). Record what you actually observe.
- [ ] The "401 without `WWW-Authenticate`" requirement conflicts with the MCP auth spec / RFC 9728 guidance and with SDK/API Gateway defaults that add the header.
- [ ] Cognito publishes OIDC discovery, not RFC 8414 `/.well-known/oauth-authorization-server`, and OIDC is listed as unsupported, so a self-hosted metadata doc is needed.
- [ ] Tools refresh only on `alexa-ai deploy`, with no warning when the server's `tools/list` has drifted.
- [ ] Auth metadata cached at deploy time: changing auth settings silently has no effect until redeploy.
- [ ] Manifest needs 6 icon sizes + a 600×900 carousel image just to deploy to the dev stage.
- [ ] The Quickstart's "MCP Apps standard" link points to the transports section of the spec, not the Apps extension.
- [ ] Does the Alexa+ client send an `Origin` header? Any non-allowed Origin gets 403 from the SDK's DNS-rebinding check (FL-005).
- [ ] Web simulator: what's visible in "response details" (tool calls? latency? raw payloads?) and what's missing for debugging.
- [ ] Local Inspector requires Node 24+ and Playwright for visual mode.
- [ ] MCP Python SDK v1 → v2 API changes (FastMCP → MCPServer; transport options moved), with many tutorials still showing v1.
