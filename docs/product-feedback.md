# Product feedback (Devpost field). Fill in one section per tool.

Answer the five required questions for each: what you used it for · what worked well · what needs work · onboarding (zero → hello world, with time) · would you build with it again (Yes/No + why). Be specific and quantified: minutes, versions, exact errors. Link friction-log IDs.

## Amazon developer tools
### Alexa+ MCP Toolkit (add-on model, MCP client behavior)
- Used for:
- Worked well:
- Needs work:
- Onboarding (time to first tool call in simulator):
- Build again?:
### Alexa AI CLI (`alexa-ai configure / new mcp / deploy / configure-account-linking`)
### Add-on Agent Skill (in Claude Code)
### Alexa+ web simulator
### Add-on Local Inspector
### MCP Apps on Alexa+ (card rendering in conversation view)

## MCP ecosystem
### MCP Python SDK v2 (MCPServer, Streamable HTTP stateless/JSON, Apps extension)
### MCP Inspector

## AWS services (**this section is the AWS Builder mini challenge answer**)
Intro sentence: "Night Watch runs entirely on AWS, provisioned with Terraform. AWS services and how they're used:"
| Service | How Night Watch uses it |
|---|---|
| AWS Lambda | MCP server (arm64, Lambda Web Adapter, provisioned concurrency) + 9 pipeline functions |
| Amazon API Gateway (HTTP API) | Public HTTPS endpoint for the MCP server and well-known metadata |
| Amazon DynamoDB | Single-table store: incidents, timelines, contacts, policies, deploy index, dedupe |
| Amazon EventBridge (bus + Scheduler) | Alert ingestion bus; polling schedules; one-time escalation timers |
| Amazon Bedrock + Strands Agents SDK | Async triage agent that narrates deterministic evidence into "just woke up" summaries |
| AWS CodeDeploy | Real deploys of the demo checkout-service; deployment events feed correlation |
| Amazon CloudWatch (alarms, EMF metrics, dashboards) + AWS X-Ray | Real p95 alarm on the demo service; Night Watch's own latency SLO |
| Amazon SNS + Amazon SES | Notification fan-out and email delivery |
| Amazon S3 + CloudFront | Raw alert archive for replay; privacy/terms/icons hosting |
| AWS Systems Manager Parameter Store | API keys and secrets |
| (if shipped) Amazon Cognito | OAuth 2.1 + PKCE account linking |
Then per service: worked well / needs work / onboarding / again?

## Third-party data
NWS API · AirNow API · NIFC WFIGS. (Not Amazon products, but say briefly how they behaved; judges like completeness.)

## Feature requests (optional field)
| Request | Why it matters for Night Watch | Priority |
|---|---|---|
| Proactive notifications from MCP add-ons (server-initiated announcement on Echo) | An incident commander should be able to wake you, not just answer | Critical |
| Negotiate and display the MCP protocol version in the simulator's response details | Debugging version mismatches | Important |
| `alexa-ai deploy --check` that diffs live `tools/list` vs deployed | Prevents stale tool caches | Important |
| First-class Cognito / OIDC discovery support for account linking | Most AWS builders already use Cognito | Important |
| Latency breakdown (network vs server vs Alexa reasoning) in the simulator | Hitting the 500 ms budget | Nice-to-have |
(Keep only the ones you believe after building.)
