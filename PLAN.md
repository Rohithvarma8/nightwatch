# Night Watch — Execution Plan (Oct 12 → Oct 23, 2026, 12:00 PM PT)

Solo entry · Alexa+ track · AWS Builder + Open Source mini challenges.
Verified against Amazon/Devpost/MCP docs on Oct 12, 2026. Re-check anything marked VERIFY.

---

## 0. Assumptions (correct me if any are wrong)

1. You already have Alexa+ builder access (the `alexa-ai` CLI and web simulator). Amazon's "Development Stages" page says you request **Private Preview** access and get credentials after approval. **If you don't have it yet, request it in the first hour today. This is the single biggest blocker.**
2. Your main repo will be **public, Apache-2.0**, from Day 1. That avoids collaborator invites expiring and satisfies "license visible in About."
3. You will **not** get US SMS working in 11 days (see Risk R6), so "text my roommate" goes out as a real push notification (ntfy) plus email (SES/SNS), behind a `Notifier` interface. SMS stays a stub.
4. The demo household lives in a Southern California county with frequent Red Flag Warnings. It's configurable.
5. Budget: AWS credits are gone (Devpost ran out Oct 7), so keep spend under about $25. Set an AWS Budget alarm on Day 1.

---

## 1. What the docs changed (verified Oct 12)

| Topic | What's true now | Impact |
|---|---|---|
| Account linking | **Optional** for MCP add-ons. Only needed if tools need user identity. | Day 1–6 run with **no auth**. Account linking is a time-boxed stretch (Day 9). |
| Unauthenticated → 401 | Required only when account linking is on. Return 401 or 403 **without** `WWW-Authenticate` when a tool is called with no valid token. | Write your own middleware. Don't use API Gateway's JWT authorizer or the MCP SDK's built-in bearer middleware. Both may emit `WWW-Authenticate` (VERIFY Day 1). |
| Auth discovery | PRM at `/.well-known/oauth-protected-resource`; AS metadata at `/.well-known/oauth-authorization-server`; must list `S256`. **DCR, CIMD, and OIDC are not supported.** Alexa caches auth metadata at deploy time. | Cognito publishes OIDC discovery, not RFC 8414. You'll need to host a small RFC 8414 doc yourself (Risk R4). |
| Latency | **Round trip under 500 ms.** | No LLM calls and no third-party HTTP in the tool hot path. Kill cold starts. |
| Protocol | Builders get spec 2025-11-25, but Amazon's own lifecycle page shows the client sending `protocolVersion: "2025-03-26"` in `initialize`. | Server must accept both. Log what you actually observe. Friction-log entry #1 is almost guaranteed. |
| Tool refresh | Alexa refreshes tools **only on `alexa-ai deploy`**. | `make deploy` must remind you to redeploy the add-on when tool schemas change. |
| Manifest | 6 light icon sizes (72, 64, 88, 126, 180, 241), at least one 600×900 carousel image, privacy + terms HTTPS URLs, 3–4 example phrases, name ≤ 30 chars. | Make the assets on Day 1 (an hour, tops). |
| Onboarding | Recommended path is the **Add-on Agent Skill** inside Claude Code. Manual path is `alexa-ai new mcp` → edit `addon.json` → `alexa-ai deploy`. | Use the Agent Skill. Its quirks are friction-log material. |
| Testing | MCP Inspector → **Local Inspector** (`addon-local-inspector <url>`, Node 24+, Playwright for visual mode; renders MCP App widgets inside device frames and checks latency) → web simulator. | Local Inspector also validates your MCP Apps card. |
| MCP spec | **2026-07-28** (stateless) is out. **Python SDK v2** is the stable line: `FastMCP` → `MCPServer`, and `stateless_http` / `json_response` moved to `run()` / `streamable_http_app()`. v2 serves old and new revisions from one endpoint. v2 has a built-in **MCP Apps** extension (`Apps`, `@apps.tool(resource_uri=...)`). | Python is clearly the right choice. Pin the exact v2 version on Day 1. |
| Open Source mini | "Create a **new, additional** open-source project or contribute to an existing public repository… alongside a primary track submission." Required: contribution URL, repo URL, GitHub username, description. Judges call "meaningful feature addition with tests" creative and "README update" obvious. | **Confirmed: licensing your main repo alone does NOT count.** You need a separate repo or an upstream PR. |
| AWS Builder | Judges call "single Bedrock call" obvious and "multi-service pipeline (Bedrock + AgentCore + Strands), agent orchestration" creative. The AWS write-up goes **inside Product Feedback**. | Use Strands + Bedrock for an async triage agent. That's a real multi-service pipeline. |
| Judging | 4 equally weighted criteria: Tech, Design, Impact, Idea. Friction logs earn up to a **+10% bonus**. Judges may skip testing and judge from text + video alone, and may use AI-driven analysis. | The video and README carry the score. Be explicit and well structured. |

---

## 2. Architecture critique

### What's right
- One engine, two sources is the strongest framing. It answers the "basic MCP wrapper" criticism head-on.
- A real CloudWatch alarm from a real bad deploy is excellent. Don't fake it.
- Terraform-everything plays to your strengths and impresses "Tech Implementation" judges.

### Gaps and fixes

**G1. The LLM can't sit in the request path.** A Bedrock call costs 400–1500 ms by itself, and the budget is 500 ms round trip.
→ Do all reasoning **at ingest time**. A Strands triage agent writes `spoken_summary`, `detail_summary`, and `recommended_actions` into DynamoDB. Tools are pure DynamoDB reads (single-digit ms) plus formatting. Target p95 under 150 ms server-side.

**G2. Cold starts.** Python + MCP SDK + pydantic + boto3 cold starts run 600 ms–1.5 s.
→ **Decision (Oct 16): no provisioned concurrency.** The demo is a recorded video, so warm the MCP function by hand (a few `tools/call` requests) right before recording. `make warm-on` exists but is optional. Original idea: arm64, lazy-import boto3 clients, and provisioned concurrency = 1 on the MCP function (about $3–6/month at 512 MB). SnapStart for Python is the alternative, but provisioned concurrency is simpler and composes cleanly with Lambda Web Adapter. Measure both on Day 2 if you have time.

**G3. Correlation must be deterministic and explainable, not "LLM magic."**
→ Use a rules engine that emits typed `Evidence` records (`deploy_proximity`, `same_service`, `geo_overlap`, `same_hazard_family`, `aqi_category`) with weights. The LLM only *narrates* that evidence and is forbidden from adding facts (enforced with a JSON-schema output check and a template fallback). This is your differentiator. Say it in the video.

**G4. Don't invent cross-domain correlation.** A wind warning doesn't cause a latency spike. The overview *ranks* both incidents. Correlation happens *within* each domain. Judges who are SREs will notice fake causality.

**G5. Notifications: SMS is a trap.** US SMS from AWS needs a registered origination identity. Toll-free verification takes weeks.
→ Use ntfy push (real phone buzz, good on video) plus SES email, fanned out from an SNS topic. Keep the `sms` channel as a documented stub.

**G6. The deploy event must come from a documented integration.**
→ The demo service is a Lambda "checkout-service" behind its own HTTP API, deployed through **CodeDeploy (Lambda alias, AllAtOnce)**. CodeDeploy deployment-state events and CloudWatch alarm state-change events both land on EventBridge natively. A load generator (EventBridge Scheduler → Lambda) gives the alarm real traffic. The "bad" version adds 900 ms of sleep to 30% of requests.

**G7. Escalation needs a timer.** Use **EventBridge Scheduler** one-time schedules: on open, schedule `escalate` at T+5 min; `acknowledge` deletes it. This is clean, serverless, and demoable ("escalation paused").

**G8. Replay mode must be honest.** Replayed alerts are real recorded payloads, time-shifted and pushed through the **same** EventBridge bus with `source=nightwatch.replay`, flagged `replay=true`. The card shows "Replay of NWS alert issued <original time>." Judges respect this. Hiding it is a risk.

**G9. Hosting on Lambda: use Lambda Web Adapter + uvicorn**, not Mangum. The SDK's Streamable HTTP app relies on ASGI lifespan, and Lambda Web Adapter runs it once per container. Fallback: Mangum with `lifespan="auto"`.

**G10. AgentCore Runtime for the MCP server: not now.** It requires inbound IAM or JWT auth on every call. That conflicts with no-auth discovery and the no-`WWW-Authenticate` rule, and it adds latency you can't afford. If you want AgentCore in the story, host the **triage agent** there as a stretch. The MCP server stays on Lambda.

**G11. Observability is part of the pitch.** EMF metrics per tool (`ToolLatencyMs`, `ToolErrors`), X-Ray, and a CloudWatch dashboard showing p95 under 500 ms. Ten seconds of that in the video beats any claim.

### Final architecture

```
                 ┌──────────── Alexa+ (web simulator) ────────────┐
                 │  MCP client (Streamable HTTP, JSON responses)  │
                 └───────────────────────┬────────────────────────┘
                                         │ HTTPS
                          API Gateway HTTP API (custom domain optional)
                                         │
                         Lambda: mcp-server (Python, MCP SDK v2,
                         Lambda Web Adapter, arm64)
                         tools = DynamoDB reads/writes only
                                         │
     ┌──────────────────────── DynamoDB (single table) ─────────────────────────┐
     └───────▲───────────────────────▲───────────────────────────▲──────────────┘
             │                       │                           │
   Lambda: triage-agent      Lambda: escalation-timer    Lambda: notifier ──► SNS ─► SES email
   (Strands + Bedrock,       (EventBridge Scheduler       (ntfy push, email,
    correlation rules,        one-time schedules)          sms stub)
    writes summaries)
             ▲
     EventBridge bus "nightwatch"
      ▲            ▲              ▲                 ▲
 Lambda:nws   Lambda:airnow  Lambda:fire(NIFC)   CloudWatch alarm state change
 (Scheduler   (Scheduler     (Scheduler)         + CodeDeploy deployment events
  5 min)       15 min)                            from demo checkout-service
      ▲
 Lambda: recorder → S3 raw archive ──► replay CLI (time-shift → same bus)

 S3 + CloudFront: privacy, terms, icons, carousel   |   CloudWatch dashboard + X-Ray
```

---

## 3. Decisions

| Decision | Choice | Why |
|---|---|---|
| Language | **Python 3.12** for the server and pipeline; **Go** for the OSS tool | SDK v2 has the MCP Apps extension built in, Strands is Python, and boto3/Bedrock are first-class. Go gives the OSS tool a single static binary for CI, and you're fluent in it. |
| Hosting | **Lambda + API Gateway HTTP API** | Fast to ship, cheap, fits Terraform. AgentCore Runtime's mandatory inbound auth fights Alexa's discovery rules (G10). |
| Transport | **Stateless Streamable HTTP + `json_response=True`** | Each POST is self-contained, so any Lambda instance can serve it. Return 405 on GET (no standalone SSE stream). You lose server→client mid-request messages (elicitation, progress), which you don't need. Must still accept `initialize` with 2025-03-26 and 2025-11-25. |
| Auth | **No auth through Day 8.** Day 9: 4-hour spike with Cognito (PKCE S256, refresh tokens) + self-hosted RFC 8414 metadata + selective 401 middleware. **If it doesn't deploy within 4 hours, drop it** and document a single demo household. | Account linking is optional per docs. It's high-risk and low-score next to the core demo. |
| Replay | Recorder starts **today**. Scenario files live in `replay/scenarios/*.json`. CLI `nw replay <scenario> --t0 -4m`. Archived NWS warnings as fallback. | Guarantees a live-looking demo on a calm day without lying. |
| Name | **Night Watch** (`name.value: "Night Watch"`) | Two common words Alexa says cleanly, fits the 3 a.m. story, under 30 chars. Backups: "Beacon", "Heads Up." Do a quick trademark/app-store search before printing icons. |
| Open Source | **`mcp-slo`**: Go CLI + GitHub Action that reliability-tests any Streamable HTTP MCP server against SLOs | Hits the "meaningful feature with tests" bar, is distinct from Amazon's Local Inspector (which validates correctness), and you dogfood it in Night Watch's CI. The hazard normalizer would be "extracted library," which is weaker for judges. Bonus: file an upstream PR for any real SDK bug you hit. |

### mcp-slo scope (2 days, hard cap)
- `mcp-slo run --url ... --concurrency 10 --duration 60s --slo p95<500ms --slo errors<1%`
- Flows: `initialize → tools/list → tools/call(<tool>, args)` with real JSON-RPC.
- **Protocol negotiation matrix:** sends `initialize` at 2025-03-26, 2025-06-18, 2025-11-25, and 2026-07-28, and reports what the server negotiates.
- **Cold vs warm:** first-request latency after an idle period (`--cold-wait 10m`, optional).
- **Auth failure modes:** missing token, malformed token, expired token → checks the status code and **flags `WWW-Authenticate` presence** (an `--profile alexa` toggle makes that a failure).
- Output: terminal table, JUnit XML, Markdown summary (`$GITHUB_STEP_SUMMARY`), exit code ≠ 0 on SLO breach.
- `action.yml` (composite or Docker), `go test` with an in-process fake MCP server, MIT license, v0.1.0 release.
- Out of scope: schema validation, UI rendering, certification checks (Local Inspector's job). Say so in the README.

---

## 4. Day-by-day plan

Every day ends with: `git push`, a friction-log pass, and 2 lines in `docs/devlog.md`.

### Day 1 · Mon Oct 12 (tonight): Spike, part A
- [ ] Confirm Alexa+ builder access. Install the `alexa-ai` CLI, run `alexa-ai configure`, install the Add-on Agent Skill and Local Inspector (Node 24+).
- [x] Create the public repo `nightwatch` (Apache-2.0, check the license shows in About). Add `CLAUDE.md` from this pack.
- [x] AWS: Budget alarm ($25), Terraform `bootstrap/` (state bucket with `use_lockfile = true`).
- [x] `server/`: MCP SDK v2 pinned (`mcp==2.3.0`); one tool `get_active_incidents` returning a hard-coded fixture; stateless + JSON responses; `/healthz`.
- [ ] Local check: `make run` → MCP Inspector lists and calls the tool.
- [ ] Start the **recorder** NOW, even as a cron on your laptop if Terraform isn't ready: NWS `alerts/active?area=CA` + AirNow every 5–15 min → S3/local JSON.
- **Deliverable:** a local MCP server works in Inspector, and the recorder is running.

### Day 2 · Tue Oct 13: Spike, part B (gate day)
- [ ] Terraform `mcp_server` + `static_site` modules: Lambda (arm64, Lambda Web Adapter; provisioned concurrency dropped, see G2) + HTTP API; S3/CloudFront with privacy/terms/icons/carousel.
- [ ] Verify by hand: `initialize` at 2025-03-26 and 2025-11-25 both succeed; GET returns 405.
- [ ] Add the auth middleware behind `AUTH_MODE=none|jwt`. In `jwt` mode, check with curl that an unauthenticated `tools/call` returns **401 with no `WWW-Authenticate`**, while `initialize`/`tools/list` still pass.
- [ ] Onboard via the Agent Skill → `addon.json` → `alexa-ai deploy`.
- [ ] **Web simulator: "what's going on?" reaches your tool.** Log the observed `protocolVersion`, headers, and latency.
- [ ] Run Local Inspector data-layer mode once and save the report.
- **GATE:** if the simulator can't reach the tool by end of day, post on the Devpost forum/Amazon support right away, keep building against Inspector, and retry daily. Don't stop the build.
- **Deliverable:** a real Alexa+ round trip on AWS, plus 2–4 friction-log entries.

### Day 3 · Wed Oct 14: Data + hazard ingestion
- [ ] Terraform `data` (DynamoDB single table + GSI1, TTL), `ingest` (EventBridge bus, Scheduler, ingester Lambdas).
- [ ] Domain models (pydantic): `Signal`, `Incident`, `Evidence`, `Contact`, `Policy`.
- [ ] Ingesters: NWS (User-Agent header, by point/zone), AirNow (API key in SSM SecureString). Normalize → `Signal` → bus.
- [ ] Idempotency: `SIGNAL#<source>#<external_id>` conditional put.
- [ ] `get_active_incidents` reads GSI1 for real.
- **Deliverable:** live NWS/AirNow signals become incidents in DynamoDB, and Alexa lists them.

### Day 4 · Thu Oct 15: Triage engine
- [ ] Correlation rules (hazard grouping by area + hazard family + time window) → `Evidence[]`.
- [ ] Severity model (NWS severity/urgency/certainty + event type + AQI category).
- [ ] Triage agent (Strands + Bedrock): writes `spoken_summary` (≤ 40 words, "just woke up" tone), `detail_summary`, `recommended_actions`. JSON-schema validated, template fallback, 8 s timeout. Pick the model by quality *and* latency; try Amazon Nova Lite first, then Claude Haiku. VERIFY model access in your region.
- [ ] Fire feed (NIFC WFIGS current incidents, distance filter). VERIFY terms.
- [ ] Tools: `explain_incident`, `get_runbook` (runbooks in `runbooks/*.yaml`).
- **Deliverable:** "what's going on?" → a grounded, short, correct briefing. "Why?" → evidence.

### Day 5 · Fri Oct 16: Actions + replay → CUT LINE A
- [ ] `acknowledge`, `escalate`, `notify_contact` (contacts with relationship aliases: "roommate," "mom").
- [ ] Notifier Lambda: ntfy + SES email via SNS; SMS stub.
- [ ] Escalation timer via EventBridge Scheduler (create on open, delete on ack).
- [ ] Replay CLI + first scenario (a recorded Red Flag Warning + AQI; archived alert as fallback).
- [ ] Full emergency flow in the simulator, end to end.
- **CUT LINE A (end of Friday): emergency readiness is a complete, submittable project.** Tag `v0.5-emergency`. If you're behind here, Days 6–7 go to polish and MCP Apps, and on-call is dropped.

### Day 6 · Sat Oct 17: On-call source
- [ ] Terraform `demo_service`: checkout Lambda + HTTP API + alias + CodeDeploy app/group; load generator on Scheduler (1 rpm × 20 requests is enough); CloudWatch alarm on p95 Duration (1-min period, 2 of 3 datapoints).
- [ ] EventBridge rules: alarm state change + CodeDeploy deployment events → normalizer → bus.
- [ ] Prod correlation: deploy proximity (alarm start − deploy end ≤ 15 min, same service) → evidence + "rollback likely" action.
- [ ] `scripts/bad_deploy.sh` / `good_deploy.sh`. Time how long the alarm takes to fire (aim for about 3–5 min).
- **Deliverable:** a real alarm caused by a real deploy, correlated and explained by Alexa.

### Day 7 · Sun Oct 18: MCP Apps card + ranking → CUT LINE B
- [ ] MCP Apps incident card (`ui://nightwatch/incidents.html`) via the SDK's `Apps` extension: severity color, title, one-line summary, evidence chips, status (Acknowledged / Escalation in 3:12), replay footer. Inline all data; no network fetches from the iframe.
- [ ] Local Inspector visual mode across device frames. Fix accessibility findings.
- [ ] Unified overview ranking (severity × recency × actionability).
- **CUT LINE B (Sunday noon):** if the on-call path isn't reliable, remove it from the demo (keep the code, label it "experimental") and move on.
- **Deliverable:** visual cards render in the simulator's conversation view.

### Day 8 · Mon Oct 19: mcp-slo, day 1
- [ ] New repo `mcp-slo` (MIT). Go module, JSON-RPC client, load runner (worker pool, HDR histogram or sorted samples), negotiation matrix, table + JSON output.
- [ ] Tests against an in-process fake server.
- **Deliverable:** `mcp-slo run` works against Night Watch prod. Paste the first p95 numbers into the devlog.

### Day 9 · Tue Oct 20: mcp-slo, day 2 + hardening + auth spike
- [ ] mcp-slo: auth-failure probes, `--profile alexa`, JUnit + Markdown summary, `action.yml`, README with a GIF, v0.1.0 release.
- [ ] Night Watch CI: run mcp-slo against the deployed endpoint on push to main. Badge in README.
- [ ] Latency hardening: trim imports, cap warm p95; warm by hand before recording (no provisioned concurrency). Screenshot the dashboard.
- [ ] **Auth spike, hard 4-hour cap** (see DESIGN.md §6). Ship it or drop it. Either way, it becomes friction-log entries.
- **Deliverable:** OSS project released; CI proves the SLO.

### Day 10 · Wed Oct 21: FEATURE FREEZE at noon → record
- [ ] Morning: bug bash in the simulator with all example phrases; fix only P0s.
- [ ] Afternoon: record. Real bad deploy (run it 2–3 times for clean takes), replay scenario, screen captures (simulator, phone notification, CloudWatch, CodeDeploy, dashboard, mcp-slo in CI). Architecture diagram as PNG.
- [ ] README: hero GIF, architecture, quickstart (`make deploy`), "How judges can test" (simulator steps plus a local Inspector path that needs no Alexa account).

### Day 11 · Thu Oct 22: Edit + write
- [ ] Edit video to ≤ 2:50 and upload to YouTube (public). Check that captions and audio have no copyrighted music.
- [ ] Devpost: description, product feedback (with the AWS Builder answer), friction log (final pass), feature requests, Open Source fields.
- [ ] **Submit a complete draft tonight.**

### Day 12 · Fri Oct 23: Submit by 10:00 AM PT
- [ ] Fresh-eyes review: repo public, license in About, MCP entry point obvious in README, video link plays logged out.
- [ ] Final submit by **10:00 AM PT** (2-hour buffer before the noon deadline). Don't touch infra afterward. Leave it running through Nov 20.

---

## 5. Top risks & mitigations

| # | Risk | Likelihood / Impact | Mitigation |
|---|---|---|---|
| R1 | No Alexa+ builder access yet | ? / Fatal | Check in the first hour. Request Private Preview now. Fallback: the rules allow a "simulated Alexa+ experience," but that's a much weaker entry. |
| R2 | Simulator can't connect (protocol/version/transport quirks) | Med / High | Day-2 gate. Capture raw requests in CloudWatch logs. Accept 2025-03-26. Ask on the forum early. |
| R3 | p95 > 500 ms (cold starts, LLM in path) | High / High | G1 + G2. Measure with mcp-slo daily. Warm by hand before recording (no provisioned concurrency). DynamoDB-only hot path. |
| R4 | Account linking: Cognito lacks RFC 8414; `resource` param handling; deploy blocked without S256 | High / Med | Optional feature. 4-hour time box. Self-host the metadata doc. Drop cleanly. |
| R5 | No real Red Flag Warning during the window | Med / Med | Recorder from Day 1 plus archived-alert fallback. Honest "replay" labeling. |
| R6 | SMS blocked (origination identity registration) | High / Low | ntfy + email. Mention SMS as future work. |
| R7 | Bad deploy → alarm takes too long or flaps | Med / Med | Tune the alarm (1-min period, 2/3). Steady load generator. Rehearse Day 6. Fallback: record with a jump cut and show timestamps. |
| R8 | LLM hallucinated facts in summaries | Med / High (trust) | Evidence-only prompt, schema validation, numeric/entity cross-check against the signal, template fallback. |
| R9 | Scope creep (rollback tool, AgentCore, Datadog, multi-household) | High / High | Cut lines A/B. Stretch list only after Day 7. |
| R10 | Third-party API terms/rate limits (NWS, AirNow, NIFC) | Low / Med | Cache, back off, proper User-Agent, attribute sources in README. |
| R11 | MCP Apps card doesn't render in the simulator | Med / Med | Text-first responses always complete. Card is an enhancement. Log the friction. |
| R12 | Running out of time on video/write-up | Med / High | Templates now. Friction log written as you go. Draft submitted Thursday. |
| R13 | AWS bill surprise | Low / Med | Budget alarm. No provisioned concurrency. Load generator stops after Nov 20. |

### Stretch list (only after Cut Line B is green)
1. `rollback_deploy` tool with explicit confirmation → triggers CodeDeploy rollback ("Alexa, roll it back").
2. Triage agent hosted on AgentCore Runtime.
3. Night Watch monitors its own SLO alarm as a prod source (dogfooding).
