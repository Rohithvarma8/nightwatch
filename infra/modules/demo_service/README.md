# demo_service

`checkout-service` (Lambda, arm64), invoked through a `live` alias from its own HTTP API (`GET /checkout`). Contents:
- **CodeDeploy** app and deployment group: AllAtOnce, no automatic rollback.
- **Load generator:** Scheduler runs it every minute, ~20 sequential requests each run. Turned off with `loadgen_enabled = false`.
- **Alarm** `nightwatch-checkout-latency-p95`: p95 Duration on `checkout-service:live`, 60 s periods, alarms on 2 of 3 above 500 ms, missing data counts as not breaching.

Terraform ignores the function's `environment` and the alias's `function_version`, because those belong to `make bad-deploy` / `make good-deploy` and CodeDeploy.

The CodeDeploy role has the actions of `AWSCodeDeployRoleForLambdaLimited`, scoped to this one function.
