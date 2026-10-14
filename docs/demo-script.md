# Demo video — script & storyboard (target 2:50, hard max 2:59)

Rules: best material first, English, no copyrighted music (silence, ambient room tone, or a royalty-free track you have rights to), no third-party trademarks beyond what's needed to show the platform. Record at 1080p. Caption every Alexa line, because the simulator is text-first. If the simulator speaks responses, capture system audio. Otherwise use on-screen text plus your own narration (say "simulator" once so nobody thinks it's faked).

| Time | Visual | Audio / on-screen text | Proof point |
|---|---|---|---|
| 0:00–0:05 | Dark room, phone on nightstand lights up: ntfy push "Night Watch: 2 active incidents" | Phone buzz. Caption: "3:02 AM" | Real notification |
| 0:05–0:12 | Screen: Alexa+ web simulator. Type/say: **"Alexa, what's going on?"** | — | Real Alexa+ round trip |
| 0:12–0:30 | Response text + **incident card** (2 rows: Red Flag Warning · high · replay footer; checkout-service latency · high) | Alexa: "Two things. A red flag wind warning for your county. No evacuation order, but air quality is moderate, so keep windows closed. Also, checkout-service latency is spiking. It started 4 minutes after the 2:51 deploy, so a rollback is the likely fix." | MCP Apps card, correlation |
| 0:30–0:38 | Title card: **Night Watch**: "One incident commander for your home and your pager." | Narration: "Home emergencies and production incidents are the same loop." | Framing |
| 0:38–0:55 | Type: **"Acknowledge the page and tell my roommate about the fire warning."** Card updates: "Acknowledged · escalation cancelled". Cut to second phone receiving the push + email | Alexa confirms both actions | Write actions, escalation timer |
| 0:55–1:20 | Type: **"Why do you think it's the deploy?"** → evidence list. Cut to the **real** CloudWatch alarm graph + CodeDeploy deployment page with matching timestamps | Alexa: "Latency p95 went from 120 to 980 milliseconds starting 2:55, four minutes after deployment v43 of checkout-service. No other service changed. Confidence: high." | Explainable, real AWS signals |
| 1:20–1:35 | Type: **"What should I do about the wind warning?"** → runbook steps (next step highlighted) | Alexa reads the next step | Runbooks |
| 1:35–1:45 | (Stretch, only if shipped) "Roll it back" → CodeDeploy rollback → alarm returns to OK | — | Agentic action |
| 1:45–2:15 | Architecture diagram, animated in 3 beats: sources → EventBridge → triage agent (Strands + Bedrock) → DynamoDB → MCP server on Lambda → Alexa+ | Narration: "Reasoning happens at ingest, so every Alexa request is a single DynamoDB read. Correlation is deterministic, and the model only narrates evidence." | AWS Builder |
| 2:15–2:30 | CloudWatch dashboard: tool p95 ~XX ms vs 500 ms line. Then GitHub Actions run of **mcp-slo** passing (negotiation matrix + SLO table) | Narration: "I open-sourced mcp-slo, the reliability tester that keeps this under Alexa's latency budget in CI." | Reliability + Open Source |
| 2:30–2:45 | Replay CLI: "Red Flag Warning replayed from real NWS alert of <date>" | Narration: "Quiet night? Replay mode feeds real recorded alerts through the same pipeline, clearly labeled." | Honesty, testability |
| 2:45–2:55 | Back to the dark room, phone dims | "Night Watch. Wake up to answers, not alerts." + repo URL | Close |

### Recording checklist
- [ ] Household/contacts are fictional (no real phone numbers or emails on screen).
- [ ] Run the bad deploy ~6 min before recording the hook so the alarm is in ALARM state.
- [ ] Clock overlay or CloudWatch timestamps match the story (or drop "3 AM" and say "tonight").
- [ ] Record 2–3 takes of each simulator exchange. Alexa+ phrasing varies, so pick the best.
- [ ] Final cut is ≤ 2:55. Watch it once with the sound off. It should still make sense.
