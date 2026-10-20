"""checkout-service: the demo prod service Night Watch watches.

Normal: ~50–150 ms per request. CHECKOUT_MODE=bad (the "bad deploy"): ~30% of requests also
sleep ~900 ms, so p95 Duration jumps above the 500 ms alarm threshold. The mode is baked into
each published Lambda version (env vars are part of a version), so a CodeDeploy alias shift is a
real deploy of a real regression.
"""

import json
import os
import random
import time

MODE = os.environ.get("CHECKOUT_MODE", "good")
SLOW_FRACTION = 0.30
SLOW_S = 0.9


def handler(event, context):
    start = time.perf_counter()
    time.sleep(random.uniform(0.05, 0.15))  # "talk to the payment provider"
    slow = MODE == "bad" and random.random() < SLOW_FRACTION
    if slow:
        time.sleep(SLOW_S)
    body = {
        "ok": True,
        "mode": MODE,
        "slow": slow,
        "version": os.environ.get("AWS_LAMBDA_FUNCTION_VERSION", "$LATEST"),
        "ms": round((time.perf_counter() - start) * 1000),
    }
    return {
        "statusCode": 200,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }
