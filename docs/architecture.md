# Architecture

Night Watch is one incident engine with two sources: home hazards (NWS alerts) and production on-call
(a CloudWatch alarm and CodeDeploy deploys from a demo service). Everything slow happens at ingest time.
When a client asks a question, the MCP server only reads DynamoDB.

![Night Watch architecture](architecture.png)

```mermaid
flowchart TB
  classDef client fill:#ede9fe,stroke:#7c3aed,color:#1e1b4b
  classDef hot fill:#dcfce7,stroke:#16a34a,color:#052e16
  classDef async fill:#e0f2fe,stroke:#0284c7,color:#082f49
  classDef store fill:#fef3c7,stroke:#d97706,color:#451a03
  classDef ext fill:#f1f5f9,stroke:#64748b,color:#0f172a
  classDef demo fill:#fee2e2,stroke:#dc2626,color:#450a0a

  subgraph HOT["Request path: DynamoDB reads only, well under the 500 ms budget"]
    direction LR
    SIM["Simulated Alexa+ client<br/>(alexa-sim, unofficial)<br/>Strands + Bedrock<br/>Polly voice, MCP Apps host"]
    APIGW["API Gateway<br/>HTTP API /mcp"]
    MCP["MCP server Lambda<br/>stateless Streamable HTTP<br/>7 tools + MCP Apps card"]
    SIM -- "MCP over HTTPS" --> APIGW --> MCP
  end

  DDB[("DynamoDB single table<br/>incidents · signals · deploys<br/>household · contacts")]
  MCP -- "reads, ack / status writes" --> DDB

  subgraph INGEST["Ingestion"]
    direction TB
    SCHED1["EventBridge Scheduler<br/>every 5 min"] --> NWS["NWS ingester Lambda<br/>api.weather.gov, zone CAZ374"]
    CWALARM["CloudWatch alarm<br/>checkout p95 > 500 ms"] --> PRODN["Prod normalizer Lambda"]
    CDEVT["CodeDeploy<br/>deployment events"] --> PRODN
  end

  BUS{{"EventBridge bus<br/>nightwatch"}}
  NWS -- "Signal" --> BUS
  PRODN -- "Signal" --> BUS

  subgraph ENGINE["Incident engine (async, at ingest time)"]
    direction TB
    BUILDER["Incident builder Lambda<br/>deterministic correlation rules<br/>typed Evidence · severity · dedupe"]
    TRIAGE["Triage agent Lambda<br/>Strands + Bedrock<br/>schema + grounding check<br/>template fallback"]
  end
  BUS -- "Signal" --> BUILDER
  BUILDER -- "IncidentChanged" --> BUS
  BUS -- "IncidentChanged" --> TRIAGE
  BUILDER --> DDB
  TRIAGE -- "grounded summary" --> DDB

  subgraph ESC["Escalation"]
    direction TB
    SCHED2["EventBridge Scheduler<br/>one-time schedule<br/>per high-severity incident"] --> ESCL["Escalation Lambda<br/>only if still open"]
  end
  BUILDER -- "start timer" --> SCHED2

  subgraph NOTIFY["Notifications"]
    direction TB
    SNS["SNS topic"] --> NOTIFIER["Notifier Lambda"]
    NOTIFIER --> NTFY["ntfy push"]
    NOTIFIER --> SES["SES email"]
  end
  ESCL --> SNS
  MCP -- "notify_contact · escalate" --> SNS

  subgraph DEMO["Demo prod service"]
    direction TB
    LOADGEN["Load generator Lambda"] --> CHECKOUT["checkout-service Lambda<br/>live alias"]
    CD["CodeDeploy<br/>bad / good deploys"] -- "deploys" --> CHECKOUT
  end
  MCP -- "rollback_deploy" --> CD
  CHECKOUT -. "latency" .-> CWALARM
  CD -. "state changes" .-> CDEVT

  class SIM client
  class APIGW,MCP hot
  class NWS,PRODN,BUILDER,TRIAGE,ESCL,NOTIFIER,SCHED1,SCHED2,SNS async
  class DDB store
  class NTFY,SES,CWALARM,CDEVT,BUS ext
  class LOADGEN,CHECKOUT,CD demo
  style HOT fill:#f0fdf4,stroke:#16a34a
  style INGEST fill:#f8fafc,stroke:#94a3b8
  style ENGINE fill:#f0f9ff,stroke:#0284c7
  style ESC fill:#f8fafc,stroke:#94a3b8
  style NOTIFY fill:#f8fafc,stroke:#94a3b8
  style DEMO fill:#fef2f2,stroke:#dc2626
```

## The paths

**Request path (green).** The simulated Alexa+ client calls the MCP server through API Gateway. Tool
handlers talk only to DynamoDB, plus SNS for `notify_contact` and `escalate` and CodeDeploy for
`rollback_deploy`. Summaries, evidence, and actions were all computed at ingest time, so a read tool is a
single DynamoDB query. There's no LLM, no third-party HTTP, and no per-request config lookup. Transport is
stateless Streamable HTTP with JSON responses. GET `/mcp` returns 405, and no response carries a
`WWW-Authenticate` header.

**Ingestion.** The NWS ingester runs every 5 minutes on EventBridge Scheduler and turns new alerts for the
household's zone into `Signal` events. The prod normalizer receives the checkout-service CloudWatch alarm
state changes and CodeDeploy deployment events through EventBridge rules, and emits the same `Signal`
shape. Replayed alerts (`make replay`) take the same path, flagged `replay=true` with the original time.

**Incident engine.** The incident builder dedupes signals, groups them into incidents by correlation key,
and runs the deterministic rules in `triage/rules.py`. For example, a Red Flag Warning plus an overlapping
Wind Advisory merge into one Fire risk incident, and an alarm shortly after a deploy becomes a deploy
regression with rollback pinned as the first action. Each rule emits typed `Evidence`. The triage agent
(Strands on Bedrock) then narrates that evidence. Its output must pass a JSON schema and a grounding check:
every number and place name has to appear in the source signals. If it fails, the incident keeps the
deterministic template and records `fallback_used=true`.

**Escalation.** For a new high-severity incident, the builder creates a one-time EventBridge Scheduler
schedule set to the household's acknowledgement timeout. When it fires, the escalation Lambda escalates
only if the incident is still open, so after `acknowledge` the timer is a no-op.

**Notifications.** `notify_contact`, `escalate`, and the escalation Lambda publish to SNS. The notifier
sends an ntfy push and an SES email. SMS is a stub.

**Demo prod service.** `checkout-service` is a real Lambda behind its own HTTP API, deployed with
CodeDeploy. The bad version sleeps about 900 ms on about 30% of requests. The load generator keeps
traffic flowing so the p95 alarm fires for real, about 2.5 minutes after a bad deploy.

## Regenerating the PNG

```sh
npx -y @mermaid-js/mermaid-cli -i docs/architecture.md -o docs/architecture.png -s 2 -b white
```

mermaid-cli writes one PNG per diagram, numbered like `architecture-1.png`. Rename it to
`architecture.png`.
