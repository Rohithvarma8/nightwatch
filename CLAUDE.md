# CLAUDE.md — Night Watch

Night Watch is an Alexa+ add-on: a self-hosted **MCP server** (Streamable HTTP, MCP spec 2025-11-25) that acts as a household incident commander. One incident engine, two sources: **home hazards** (NWS alerts, AirNow AQI, NIFC fire incidents) and **production on-call** (CloudWatch alarms + CodeDeploy deploys from a demo service). Loop: Ingest → Normalize → Correlate → Assess severity → Summarize → Runbook → Notify/Escalate.

Hackathon entry, solo, deadline **Oct 23 2026 12:00 PT**. Optimize for: a working demo, correctness, latency, clarity. Not for: generality, multi-tenant scale.

Design references: `docs/architecture.md`, `DESIGN.md` (tool schemas, data model), `PLAN.md` (what's in scope today).

## Non-negotiable rules
1. **Latency budget: Alexa requires < 500 ms round trip.** MCP tool handlers may call **DynamoDB only**. No Bedrock, no third-party HTTP, no SSM/Secrets lookups per request (load config at init). Target p95 < 150 ms server-side.
2. **LLMs never run in the request path.** Summaries are produced asynchronously by the triage agent at ingest time and stored on the incident.
3. **LLM output narrates evidence; it never adds facts.** Triage output is JSON-schema validated. Numbers and place names must appear in the source signals. On any failure, use the deterministic template in `triage/templates.py` and set `summarizer.fallback_used=true`.
4. **Correlation is deterministic** (`triage/rules.py`) and emits typed `Evidence` records. No cross-domain causal claims (weather does not cause latency).
5. **Transport is stateless Streamable HTTP with JSON responses.** GET `/mcp` → 405. Must accept `initialize` with protocolVersion `2025-03-26` **and** `2025-11-25` (the Alexa+ client has been documented sending 2025-03-26).
6. **Unauthenticated → HTTP 401 with NO `WWW-Authenticate` header** (Alexa+ requirement). Never use API Gateway JWT authorizers or SDK auth middleware that adds that header. Auth lives in `server/src/nightwatch/middleware/auth.py`, toggled by `AUTH_MODE=none|jwt`.
7. **Replay honesty:** replayed signals carry `replay=true` and `replay_original_time`, and the UI shows it. Never strip these flags.
8. Every tool returns short spoken-friendly `content` text **and** `structuredContent`. ≤ 40 words per incident. Never read IDs aloud.
9. **Changing a tool's name, description, or schema requires `alexa-ai deploy`.** Alexa refreshes tools only on deploy. Remind the human in your summary whenever you change one.
10. No secrets in git. Use SSM SecureString (AirNow key, ntfy topic) and env vars locally via `.env` (gitignored).

## Stack
- Python 3.12, `uv`, **MCP Python SDK v2** (pinned exact version in `server/pyproject.toml`; class is `MCPServer`, MCP Apps via the SDK `Apps` extension). Check the official docs at py.sdk.modelcontextprotocol.io before using an API you're unsure of. Don't use v1 `FastMCP` examples.
- pydantic v2, boto3, aws-lambda-powertools (logger, metrics/EMF, tracer), Strands Agents SDK + Amazon Bedrock (triage only).
- Lambda (arm64) + Lambda Web Adapter + uvicorn; API Gateway HTTP API; DynamoDB single table; EventBridge bus + Scheduler; SNS/SES; CodeDeploy; CloudWatch; X-Ray.
- Terraform ≥ 1.10, AWS provider pinned in `infra/envs/dev/versions.tf`.
- Node 24+ only for MCP Inspector / Alexa Local Inspector tooling.

## Layout
```
server/      MCP server — entry point server/src/nightwatch/app.py
pipeline/    async Lambdas: ingest/, triage/, escalation/, notify/, recorder/, replay/
demo-service/ checkout Lambda + loadgen + bad/good deploy scripts
runbooks/    YAML runbooks     replay/scenarios/  recorded real payloads
infra/       Terraform: bootstrap/, modules/*, envs/dev/
addon/       Alexa+ add-on package (addon.json) — edit via alexa-ai / Agent Skill
site/        privacy, terms, icons, carousel (served by CloudFront)
docs/        architecture, friction-log, product-feedback, devpost, devlog
```
Layering inside `server/`: `tools/` (thin) → `domain/` (pure logic, no I/O) → `store/` (only module that touches DynamoDB). Tools never import boto3 directly.

## Commands
```
make setup          # uv sync both packages, pre-commit install
make lint           # ruff check + ruff format --check + pyright
make test           # pytest -q (unit + contract + negotiation), terraform fmt -check, tflint
make run            # uvicorn locally on :8080 (DynamoDB Local via docker compose, or AWS dev table with AWS_PROFILE)
make inspect        # npx @modelcontextprotocol/inspector → http://localhost:8080/mcp
make tunnel         # cloudflared tunnel for testing the local server from Alexa
make build          # build Lambda zips (aarch64 wheels) into dist/
make deploy         # build + terraform apply (envs/dev) + print MCP URL; prints REDEPLOY ADD-ON warning if tool schemas changed
make addon-deploy   # cd addon && alexa-ai deploy
make local-inspect  # addon-local-inspector $(MCP_URL)
make replay SCENARIO=redflag-xxxx T0=-4m
make bad-deploy / make good-deploy   # demo-service via CodeDeploy
make slo            # mcp-slo run --url $(MCP_URL) --profile alexa --slo 'p95<500ms'
```
`make deploy` computes a hash of all tool definitions (`scripts/tool_hash.py`) and warns if it differs from `addon/.last_deployed_tool_hash`.

## Testing approach
- **Unit:** domain logic (severity, ranking, correlation rules, spoken formatting, template fallback) with table-driven tests. Fixtures in `tests/fixtures/` are real recorded payloads.
- **Contract:** spin up the ASGI app in-process and use the SDK's client over Streamable HTTP: `initialize` (both protocol versions), `tools/list` snapshot test (schema changes must be deliberate: update the snapshot and redeploy the add-on), `tools/call` for every tool, error paths.
- **Auth:** with `AUTH_MODE=jwt`, unauthenticated `tools/call` → 401, and the response must NOT contain `WWW-Authenticate`; `initialize`/`tools/list` → 200.
- **Latency:** a contract test asserts each tool handler completes in < 50 ms against moto/DynamoDB Local; prod is checked by `make slo`.
- **Triage:** Bedrock is mocked in tests. A golden-file test makes sure every number and place name in the summary appears in the input signals.
- **Infra:** `terraform validate`, `tflint`, and `plan` in CI (no auto-apply).
- Before saying a task is done: `make lint test` passes. If the change touches the hot path, run `make slo` against dev and report p95.

## Conventions
- Type hints everywhere; pyright basic must pass. ruff (line length 100).
- Timestamps: UTC ISO-8601 in storage, local time (household tz) only in spoken text ("2:51 AM").
- IDs: ULIDs with prefixes (`inc_`, `sig_`, `evt_`).
- Logging: powertools structured JSON with `incident_id`, `tool`, `latency_ms`. Never log tokens or contact details.
- Metrics (EMF, namespace `NightWatch`): `ToolLatencyMs{tool}`, `ToolErrors{tool}`, `IngestLagSeconds{source}`, `TriageFallback`.
- Tool descriptions are product copy. Write them for Alexa's reasoning: when to use, what it returns.
- Small PR-sized commits with conventional commit messages.

## Friction log habit (important: judging bonus)
When anything Amazon/AWS/MCP-tooling related surprises you or the human (errors, doc gaps, mismatched behavior, workarounds), append an entry to `docs/friction-log.md` using the template in that file **in the same session**, with the exact command, the error text, and the workaround. Facts only. If unsure whether it's our bug or theirs, say so.

## Don't
- Don't add an LLM call, network call, or new AWS client to a tool handler.
- Don't add a `WWW-Authenticate` header, SSE GET stream, or session state.
- Don't rename tools casually (Alexa caches them until redeploy).
- Don't fake data in the prod path. Demo alarms come from the real demo service.
- Don't expand scope beyond today's PLAN.md section without asking.
- Don't create NAT gateways or VPC-attached Lambdas; budget is ~$25.
- No always-on compute, except provisioned concurrency = 1 on the MCP function's live alias during demo recording (Oct 20–22) and judging (Nov 9–20). Toggle with `make warm-on` / `make warm-off`.
