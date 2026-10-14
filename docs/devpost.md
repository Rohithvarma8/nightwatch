# Devpost write-up template

**Project name:** Night Watch
**Tagline (≤ 200 chars):** An Alexa+ incident commander for your home and your pager: real alerts, correlated and explained, with one-sentence actions you can take half-asleep.

## Inspiration
(2–3 sentences.) As an SRE, the worst part of a 3 AM page isn't fixing it. It's the first five minutes of figuring out what's going on. Households in wildfire country face the same problem with warnings, smoke, and evacuation rumors. Same loop, different stakes.

## What it does
- Ask "Alexa, what's going on?" and get a ranked briefing across home hazards (NWS warnings, air quality, nearby fires) and production incidents (CloudWatch alarms + deploys).
- "Why?" returns explainable evidence, not vibes ("latency rose 4 minutes after deploy v43; no other service changed").
- Acknowledge, escalate, get the runbook's next step, and notify a contact by voice. Escalation timers fire automatically if nobody acknowledges.
- Visual incident cards via MCP Apps in the Alexa+ conversation view.
- Replay mode feeds real recorded alerts through the same pipeline, clearly labeled.

## How we built it
Architecture diagram + 1 paragraph: ingest → EventBridge → deterministic correlation → Strands/Bedrock triage agent writes summaries at ingest → DynamoDB → stateless MCP server on Lambda (p95 XX ms vs Alexa's 500 ms budget). All Terraform. CI runs mcp-slo against the live endpoint.
**Where the MCP entry point lives:** `server/src/nightwatch/app.py` (Streamable HTTP, MCP spec 2025-11-25, tools: …).

## Challenges we ran into
(Pull the 3 best friction-log entries: protocol negotiation, 401 semantics, latency.)

## Accomplishments we're proud of
Real alarms from real deploys. A sub-150 ms hot path. Explainability by construction. An open-source reliability tool.

## What we learned

## What's next
Proactive announcements (if Alexa+ exposes them), PagerDuty/Opsgenie sources, multi-household onboarding via account linking, SMS once registered.

## Built with
python, go, mcp, alexa-plus, aws-lambda, amazon-api-gateway, amazon-dynamodb, amazon-eventbridge, amazon-bedrock, strands-agents, aws-codedeploy, amazon-cloudwatch, amazon-sns, amazon-ses, amazon-s3, amazon-cloudfront, terraform, github-actions

## Testing instructions for judges
1. Watch the video (2:5x).
2. Local path (no Alexa account needed): `git clone … && make setup && make run && make inspect`, then call `get_active_incidents` with replay data (`make replay SCENARIO=…` against local).
3. Live endpoint: `<MCP URL>` (no auth). Try it with MCP Inspector.
4. Alexa+ simulator: add-on "Night Watch" in development stage (explain how judges can access it, or state it's shown in the video).

---
## Track & mini challenges
- Primary track: **Alexa+**
- Mini challenges: **AWS Builder**, **Open Source**

## Open Source fields
- **Contribution URL:** https://github.com/<you>/mcp-slo/releases/tag/v0.1.0 (plus any upstream PR URL)
- **Project repository URL:** https://github.com/<you>/mcp-slo
- **GitHub username:** <you>
- **Description (what / how / why):** mcp-slo is a Go CLI and GitHub Action that reliability-tests any Streamable HTTP MCP server against SLOs: concurrent load with p50/p95/p99 latency, a protocol-version negotiation matrix (2025-03-26 → 2026-07-28), cold-vs-warm latency, and auth failure-mode probes, including an Alexa+ profile that flags `WWW-Authenticate` on 401s. It complements Amazon's Local Inspector (which checks correctness and rendering) by checking performance and resilience in CI, and it fails the build when the server would blow Alexa's 500 ms budget. Built during the hackathon, MIT licensed, with tests and a GitHub Action used by Night Watch's own CI.
