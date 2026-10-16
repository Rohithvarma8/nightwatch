SERVER := server
PORT   ?= 8080
MCP_URL ?= http://localhost:$(PORT)/mcp
TF_DEV  := infra/envs/dev

.PHONY: setup lint test run inspect build deploy

setup:  ## Install server deps (uv)
	cd $(SERVER) && uv sync

lint:  ## ruff + pyright
	cd $(SERVER) && uv run ruff check . && uv run ruff format --check . && uv run pyright

test:  ## pytest (unit + contract)
	cd $(SERVER) && uv run pytest -q

run:  ## MCP server on :$(PORT)
	cd $(SERVER) && uv run uvicorn nightwatch.app:asgi --host 127.0.0.1 --port $(PORT)

inspect:  ## MCP Inspector against the local server
	@echo "Transport: Streamable HTTP   URL: $(MCP_URL)"
	npx -y @modelcontextprotocol/inspector

build:  ## Lambda zip (aarch64 manylinux wheels) -> dist/mcp_server.zip
	scripts/build_mcp_server.sh

deploy: build  ## build + terraform apply (envs/dev) + print the MCP URL
	terraform -chdir=$(TF_DEV) init -input=false
	terraform -chdir=$(TF_DEV) apply
	@echo "MCP URL: $$(terraform -chdir=$(TF_DEV) output -raw mcp_url)"
