#!/usr/bin/env bash
# Real deploy of checkout-service through CodeDeploy (AllAtOnce, no automatic rollback).
#   scripts/deploy_checkout.sh good|bad
# Sets CHECKOUT_MODE on $LATEST, publishes a version (env is part of a version), and starts a
# CodeDeploy deployment that moves the `live` alias to it. `good` is the rollback.
set -euo pipefail

MODE="${1:?usage: deploy_checkout.sh good|bad}"
[[ "$MODE" == good || "$MODE" == bad ]] || { echo "mode must be good or bad"; exit 2; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TF=(terraform -chdir="$ROOT/infra/envs/dev" output -raw)
AWS=(--profile nightwatch --region us-west-2)
FN=checkout-service
APP="$("${TF[@]}" codedeploy_app)"
GROUP="$("${TF[@]}" codedeploy_group)"

aws lambda update-function-configuration "${AWS[@]}" --function-name "$FN" \
  --environment "Variables={CHECKOUT_MODE=$MODE}" >/dev/null
aws lambda wait function-updated "${AWS[@]}" --function-name "$FN"
TARGET="$(aws lambda publish-version "${AWS[@]}" --function-name "$FN" \
  --description "checkout-service ($MODE)" --query Version --output text)"
CURRENT="$(aws lambda get-alias "${AWS[@]}" --function-name "$FN" --name live \
  --query FunctionVersion --output text)"
if [ "$TARGET" = "$CURRENT" ]; then
  echo "live is already v$CURRENT ($MODE); nothing to deploy"
  exit 0
fi

REVISION="$(python3 - "$FN" "$CURRENT" "$TARGET" <<'PY'
import json, sys
fn, current, target = sys.argv[1:]
appspec = {"version": 0.0, "Resources": [{"checkout": {"Type": "AWS::Lambda::Function",
    "Properties": {"Name": fn, "Alias": "live", "CurrentVersion": current, "TargetVersion": target}}}]}
print(json.dumps({"revisionType": "AppSpecContent", "appSpecContent": {"content": json.dumps(appspec)}}))
PY
)"
DEPLOYMENT="$(aws deploy create-deployment "${AWS[@]}" --application-name "$APP" \
  --deployment-group-name "$GROUP" --revision "$REVISION" \
  --description "$MODE deploy: v$CURRENT -> v$TARGET" --query deploymentId --output text)"
echo "deployment $DEPLOYMENT: $FN live v$CURRENT -> v$TARGET ($MODE), started $(date -u +%H:%M:%SZ)"
aws deploy wait deployment-successful "${AWS[@]}" --deployment-id "$DEPLOYMENT"
echo "deployment $DEPLOYMENT succeeded at $(date -u +%H:%M:%SZ)"
