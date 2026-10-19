# triage

Async triage agent (Strands Agents + Amazon Bedrock). The incident builder publishes
`IncidentChanged` to the bus. This Lambda then:
1. loads the incident and the full text of its current signals
2. asks the model for JSON: `spoken_summary` (≤ 40 words), `detail_summary`, `recommended_actions` (≤ 3)
3. validates the JSON against the schema and runs the grounding check (every number, time word and place name must appear in the source)
4. writes the summary back only if the incident's `content_hash` hasn't changed since

Models: `model_id` (Nova Lite) first, then `fallback_model_id` (Claude Haiku), within one 8 s budget. If both fail, the deterministic template stays and `summarizer.fallback_used = true`.

- IAM: `bedrock:InvokeModel` only on those models' ARNs (an inference profile also needs its foundation-model ARNs); table access is scoped to `INC#*` and `SIG#*` (read/update) plus `HH#*` (GetItem only, for the household time zone).
- The MCP server never calls Bedrock.
- No reserved concurrency, because the account's concurrency limit is 10 and AWS keeps 10 unreserved.
