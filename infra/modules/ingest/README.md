# ingest

The signal pipeline:

```
Scheduler (rate 5 min) ─► nightwatch-ingest-nws ─► api.weather.gov/alerts/active?point=lat,lon
                              │ normalize → Signal, conditional put SIG#nws#<id> (TTL 7 d)
                              ▼
                    EventBridge bus "nightwatch"  ◄── make replay (same path, replay=true)
                              │ rule: detail-type = Signal
                              ▼
                   nightwatch-incident-builder ─► OPENKEY lookup → create/update incident (GSI1)
Scheduler (rate 5 min, {"action":"sweep"}) ─┘     sweep: alert ended → resolve, drop GSI1 + OPENKEY
```

- Both Lambdas run python3.12 on arm64 with 7-day log retention and share `dist/pipeline.zip`.
- IAM uses `dynamodb:LeadingKeys` scoping:
  - ingester: `HH#*` reads and `SIG#*` writes
  - builder: `HH#*` and `INC#*` writes, plus Query on GSI1
- `nws_user_agent` comes from the gitignored `envs/dev/terraform.tfvars`.
- AirNow is not built yet (TODO).
