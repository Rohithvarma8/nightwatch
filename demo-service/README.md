# demo-service

The prod source for Night Watch's on-call demo. All of it is real: a real Lambda, real deploys, a real alarm.

- `checkout/`: `checkout-service`, behind its own HTTP API, invoked through the `live` alias.
  - Normal requests take about 50–150 ms.
  - With `CHECKOUT_MODE=bad`, about 30% of requests sleep an extra ~900 ms.
- `loadgen/`: EventBridge Scheduler runs it every minute; each run sends ~20 sequential requests.
  - Terraform variable `loadgen_enabled` turns it off.
- `make bad-deploy` / `make good-deploy` (`scripts/deploy_checkout.sh`):
  - sets the mode on `$LATEST`, publishes a version, and starts a CodeDeploy deployment (AllAtOnce, no automatic rollback) that moves `live` to it
  - prints the deployment ID
  - `good-deploy` is the rollback.
- The CloudWatch alarm `nightwatch-checkout-latency-p95` watches p95 Duration on `checkout-service:live`: 60 s periods, alarm on 2 of 3 above 500 ms, missing data counts as not breaching.
