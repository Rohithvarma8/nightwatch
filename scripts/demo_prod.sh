#!/usr/bin/env bash
# Demo prod incident (dev): load generator on → stable baseline → bad deploy → ALARM expected.
#   scripts/demo_prod.sh        (turn the load generator off afterwards: make demo-prod-off)
# The terraform apply is interactive: review the plan (load generator schedule only) and type yes.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TF_DIR="$ROOT/infra/envs/dev"
TFVARS="$TF_DIR/terraform.tfvars"
AWS=(--profile nightwatch --region us-west-2)
FN=checkout-service
ALARM=nightwatch-checkout-latency-p95
THRESHOLD_MS=500
BASELINE_MIN=3          # consecutive one-minute periods with traffic and p95 under the threshold
MIN_SAMPLES=10          # the load generator sends ~20 requests/min
TIMEOUT_S="${DEMO_BASELINE_TIMEOUT_S:-720}"

state="$(aws cloudwatch describe-alarms "${AWS[@]}" --alarm-names "$ALARM" \
  --query 'MetricAlarms[0].StateValue' --output text)"
if [ "$state" = "ALARM" ]; then
  echo "alarm $ALARM is already in ALARM; run make good-deploy and wait for OK first"; exit 1
fi

if grep -Eq '^loadgen_enabled *= *true' "$TFVARS"; then
  echo "load generator already enabled in terraform.tfvars"
else
  sed -i '' -E 's/^(loadgen_enabled *= *)false/\1true/' "$TFVARS"
  echo "set loadgen_enabled = true in terraform.tfvars"
fi
terraform -chdir="$TF_DIR" apply

echo "waiting for a stable baseline: $BASELINE_MIN one-minute periods, >= $MIN_SAMPLES requests, p95 < ${THRESHOLD_MS} ms"
deadline=$(( $(date +%s) + TIMEOUT_S ))
while :; do
  start="$(date -u -v-12M +%Y-%m-%dT%H:%M:00Z)"
  end="$(date -u +%Y-%m-%dT%H:%M:00Z)"  # whole minutes only: the current one is still filling
  verdict="$(aws cloudwatch get-metric-statistics "${AWS[@]}" --namespace AWS/Lambda \
    --metric-name Duration --dimensions Name=FunctionName,Value=$FN Name=Resource,Value=$FN:live \
    --start-time "$start" --end-time "$end" --period 60 \
    --statistics SampleCount --extended-statistics p95 --output json | python3 -c '
import json, sys
need, samples, limit = (int(a) for a in sys.argv[1:])
points = sorted(json.load(sys.stdin)["Datapoints"], key=lambda p: p["Timestamp"])[-need:]
row = ["%s p95=%.0fms n=%d" % (p["Timestamp"][11:16], p["ExtendedStatistics"]["p95"], p["SampleCount"]) for p in points]
ok = len(points) == need and all(p["SampleCount"] >= samples and p["ExtendedStatistics"]["p95"] < limit for p in points)
print(("OK " if ok else "WAIT ") + (", ".join(row) or "no datapoints yet"))
' "$BASELINE_MIN" "$MIN_SAMPLES" "$THRESHOLD_MS")"
  echo "  $(date +%H:%M:%S) $verdict"
  [[ "$verdict" == OK* ]] && break
  if [ "$(date +%s)" -ge "$deadline" ]; then echo "FAIL: no stable baseline within ${TIMEOUT_S}s"; exit 1; fi
  sleep 30
done

"$ROOT/scripts/deploy_checkout.sh" bad
# Day 6 timings: ALARM came 1 min 51 s to 2 min 10 s after the bad deploy finished.
echo "ALARM expected around $(date -v+110S +%H:%M:%S)–$(date -v+160S +%H:%M:%S) local (~2 min after the deploy finished)."
echo "The incident appears within ~1 s of ALARM. Afterwards: make demo-prod-off (or roll back first)."
