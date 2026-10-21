# Night Watch

A household incident commander built as an Alexa+ add-on: a self-hosted MCP server on AWS
(Lambda + API Gateway + DynamoDB) with seven tools and an MCP Apps incident card. One incident
engine, two sources: home hazards (NWS alerts) and production on-call (CloudWatch alarm +
CodeDeploy deploys from a demo service). See `docs/architecture.md`, `DESIGN.md`, and `PLAN.md`.

## Simulated Alexa+ client (unofficial)

The Alexa+ developer tools are in partner preview and not available to hackathon participants
(organizers confirmed on the Devpost forum, topic 45262), so the demo uses `alexa-sim/`: a local,
clearly labeled, **unofficial** simulated client that talks to the **real** deployed Night Watch
MCP server. Nothing is mocked.

- **Agent:** Strands on Amazon Bedrock (Claude Haiku 4.5, Amazon Nova Lite fallback), connected to
  the live MCP URL over Streamable HTTP. Voice-assistant prompt: 1–3 spoken sentences, no IDs or
  URLs, facts only from tool results. `rollback_deploy`, `notify_contact`, and `escalate` need a
  "yes" first; the backend also refuses those calls on any turn that isn't a yes.
- **Voice:** Chrome speech input (Web Speech API) or the text box; replies spoken with Amazon Polly
  (neural).
- **Screen:** transcript, spoken reply, a "tools called" strip with each MCP round trip, and the
  MCP Apps card in a sandboxed iframe (`resources/read` → `ui/initialize` →
  `ui/notifications/tool-result`).

### Run it

Needs `uv`, Terraform state for `infra/envs/dev`, and the `nightwatch` AWS profile with Bedrock
`InvokeModel` and Polly `SynthesizeSpeech` in us-west-2.

```
cd alexa-sim && uv sync && cd ..
make sim          # http://localhost:8765 (open in Chrome; allow the microphone)
make sim-smoke    # the demo turns, printed with tools called and latency
```

`make sim-smoke` has **real side effects**: the "yes" turns notify the demo contact and start a
CodeDeploy rollback of `checkout-service`. It needs live incidents. Run `make replay FILE=…` for
the fire-risk incident, and to get the prod incident turn on the load generator, then run
`make bad-deploy`.

Configuration (environment): `SIM_MODEL`, `SIM_FALLBACK_MODEL`, `SIM_VOICE` (default `Joanna`),
`SIM_PORT` (default 8765).
