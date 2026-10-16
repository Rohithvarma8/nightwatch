#!/usr/bin/env bash
# Package a Python project for Lambda (python3.12, arm64) → dist/<name>.zip.
#   scripts/build_lambda.sh server   mcp_server nightwatch          (MCP server, adds run.sh)
#   scripts/build_lambda.sh pipeline pipeline   nightwatch_pipeline (ingest + incident builder)
# Deps come from the project's uv.lock as aarch64 manylinux wheels only (no local compiles).
# nightwatch-core (shared/) is a local path dep, so it's copied in as source.
# boto3 isn't bundled: the Lambda python3.12 runtime provides it.
set -euo pipefail

PROJECT="$1"
NAME="$2"
MODULE="$3"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST="$ROOT/dist"
PKG="$DIST/$NAME"
ZIP="$DIST/$NAME.zip"

rm -rf "$PKG" "$ZIP"
mkdir -p "$PKG"

(cd "$ROOT/$PROJECT" && uv export --frozen --no-dev --no-emit-project \
  --no-emit-package nightwatch-core --no-hashes \
  --format requirements.txt -o "$DIST/$NAME.requirements.txt" -q)

uvx --python 3.12 pip install -q \
  --platform manylinux2014_aarch64 --implementation cp --python-version 3.12 \
  --only-binary=:all: --no-compile \
  --target "$PKG" -r "$DIST/$NAME.requirements.txt"

cp -R "$ROOT/$PROJECT/src/$MODULE" "$PKG/"
cp -R "$ROOT/shared/src/nightwatch_core" "$PKG/"
find "$PKG" -name __pycache__ -type d -prune -exec rm -rf {} +

if [ "$NAME" = "mcp_server" ]; then
  cat > "$PKG/run.sh" <<'SH'
#!/bin/bash
# Lambda handler: Lambda Web Adapter (AWS_LAMBDA_EXEC_WRAPPER=/opt/bootstrap) runs this.
PATH=$PATH:$LAMBDA_TASK_ROOT/bin \
  PYTHONPATH=$PYTHONPATH:/opt/python:$LAMBDA_RUNTIME_DIR \
  exec python -m uvicorn --host 127.0.0.1 --port "${AWS_LWA_PORT:-8080}" nightwatch.app:asgi
SH
  chmod +x "$PKG/run.sh"
fi

# /var/task is read-only, so precompile. Hash-based pycs + fixed mtimes keep the zip
# reproducible: no code change → same hash → terraform has nothing to update.
(cd "$ROOT/$PROJECT" && uv run --frozen python -m compileall -q -j 0 \
  --invalidation-mode unchecked-hash "$PKG" >/dev/null)
find "$PKG" -exec touch -h -t 202601010000 {} +
(cd "$PKG" && find . -type f -o -type l | LC_ALL=C sort | zip -q -X -y "$ZIP" -@)

echo "built $ZIP ($(du -h "$ZIP" | cut -f1))"
