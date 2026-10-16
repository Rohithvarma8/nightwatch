SERVER := server
PORT   ?= 8080
MCP_URL ?= http://localhost:$(PORT)/mcp
TF_DEV  := infra/envs/dev
# Local, gitignored toggle; terraform loads *.auto.tfvars on every apply, so `make deploy` keeps it.
WARM_TFVARS := $(TF_DEV)/warm.auto.tfvars

.PHONY: setup lint test run inspect build deploy warm-on warm-off

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

warm-on: build  ## provisioned concurrency = 1 on the live alias (demo recording Oct 20-22, judging Nov 9-20 ONLY; bills always-on)
	echo 'provisioned_concurrency = 1' > $(WARM_TFVARS)
	terraform -chdir=$(TF_DEV) init -input=false
	terraform -chdir=$(TF_DEV) apply

warm-off: build  ## provisioned concurrency = 0 (back to on-demand, no always-on cost)
	echo 'provisioned_concurrency = 0' > $(WARM_TFVARS)
	terraform -chdir=$(TF_DEV) init -input=false
	terraform -chdir=$(TF_DEV) apply
