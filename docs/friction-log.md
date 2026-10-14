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
