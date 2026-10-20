"""Load generator: ~20 sequential requests to checkout-service per invocation (Scheduler, 1/min).

Sequential on purpose: concurrency 1 keeps the account's small Lambda concurrency pool free.
"""

import json
import os
import time
import urllib.request

URL = os.environ["CHECKOUT_URL"]
REQUESTS = int(os.environ.get("REQUESTS", "20"))
TIMEOUT_S = 5


def handler(event, context):
    latencies, errors = [], 0
    for _ in range(REQUESTS):
        if context and context.get_remaining_time_in_millis() < 3000:
            break  # never run into the function timeout
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(URL, timeout=TIMEOUT_S) as resp:  # noqa: S310 (our API)
                resp.read()
        except Exception:
            errors += 1
        latencies.append(round((time.perf_counter() - start) * 1000))
    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95) - 1] if latencies else None
    result = {
        "requests": len(latencies),
        "errors": errors,
        "p50_ms": latencies[len(latencies) // 2] if latencies else None,
        "p95_ms": p95,
    }
    print(json.dumps(result))
    return result
