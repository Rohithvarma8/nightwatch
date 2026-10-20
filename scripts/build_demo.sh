#!/usr/bin/env bash
# Demo service Lambdas (stdlib only) → dist/checkout.zip, dist/loadgen.zip (reproducible).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/dist"
for fn in checkout loadgen; do
  rm -f "$ROOT/dist/$fn.zip"
  (cd "$ROOT/demo-service/$fn" && touch -t 202601010000 app.py && zip -q -X "$ROOT/dist/$fn.zip" app.py)
  echo "built $ROOT/dist/$fn.zip"
done
