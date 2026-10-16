#!/usr/bin/env bash
# Package the MCP server for Lambda (python3.12, arm64) → dist/mcp_server.zip.
# Deps come from uv.lock as aarch64 manylinux wheels only (no local compiles).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST="$ROOT/dist"
PKG="$DIST/mcp_server"
ZIP="$DIST/mcp_server.zip"

rm -rf "$PKG" "$ZIP"
mkdir -p "$PKG"

(cd "$ROOT/server" && uv export --frozen --no-dev --no-emit-project --no-hashes \
  --format requirements.txt -o "$DIST/mcp_server.requirements.txt" -q)

uvx --python 3.12 pip install -q \
  --platform manylinux2014_aarch64 --implementation cp --python-version 3.12 \
  --only-binary=:all: --no-compile \
  --target "$PKG" -r "$DIST/mcp_server.requirements.txt"

cp -R "$ROOT/server/src/nightwatch" "$PKG/"
find "$PKG" -name __pycache__ -type d -prune -exec rm -rf {} +

cat > "$PKG/run.sh" <<'SH'
#!/bin/bash
# Lambda handler: Lambda Web Adapter (AWS_LAMBDA_EXEC_WRAPPER=/opt/bootstrap) runs this.
PATH=$PATH:$LAMBDA_TASK_ROOT/bin \
  PYTHONPATH=$PYTHONPATH:/opt/python:$LAMBDA_RUNTIME_DIR \
  exec python -m uvicorn --host 127.0.0.1 --port "${AWS_LWA_PORT:-8080}" nightwatch.app:asgi
SH
chmod +x "$PKG/run.sh"

# /var/task is read-only, so precompile. Hash-based pycs + fixed mtimes keep the zip
# reproducible: no code change → same hash → terraform has nothing to update.
(cd "$ROOT/server" && uv run --frozen python -m compileall -q -j 0 \
  --invalidation-mode unchecked-hash "$PKG" >/dev/null)
find "$PKG" -exec touch -h -t 202601010000 {} +
(cd "$PKG" && find . -type f -o -type l | LC_ALL=C sort | zip -q -X -y "$ZIP" -@)

echo "built $ZIP ($(du -h "$ZIP" | cut -f1))"
