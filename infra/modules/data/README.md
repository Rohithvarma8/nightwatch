# data

DynamoDB single table `nightwatch` (DESIGN.md §3): on-demand, `PK`/`SK` strings, sparse `GSI1`
(`GSI1PK`/`GSI1SK`) for active incidents, TTL on `expires_at`, PITR off.

| Item | PK | SK |
|---|---|---|
| Household | `HH#<hid>` | `PROFILE` |
| Incident | `INC#<iid>` | `META` (+ `GSI1PK=HH#<hid>#ACTIVE`, `GSI1SK=<sevRank>#<startedAt>` while active) |
| Incident event | `INC#<iid>` | `EVT#<ts>#<eid>` |
| Signal dedupe | `SIG#<source>#<extId>` | `META` (TTL 7 days) |
| Open incident by key | `HH#<hid>` | `OPENKEY#<correlationKey>` |

Outputs: `table_name`, `table_arn`, `gsi1_arn`.
