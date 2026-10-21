SERVER := server
PACKAGES := shared pipeline server alexa-sim
PORT   ?= 8080
SIM_PORT ?= 8765
MCP_URL ?= http://localhost:$(PORT)/mcp
TF_DEV  := infra/envs/dev
# Local, gitignored toggle; terraform loads *.auto.tfvars on every apply, so `make deploy` keeps it.
WARM_TFVARS := $(TF_DEV)/warm.auto.tfvars
AWS_ENV := AWS_PROFILE=nightwatch AWS_DEFAULT_REGION=us-west-2
TF_OUT   = terraform -chdir=$(CURDIR)/$(TF_DEV) output -raw

.PHONY: setup lint test run inspect build deploy warm-on warm-off seed-household replay reset-incidents smoke bad-deploy good-deploy sim sim-smoke

setup:  ## Install deps for shared/, pipeline/, server/ (uv)
	for p in $(PACKAGES); do (cd $$p && uv sync --all-extras) || exit 1; done

lint:  ## ruff + pyright (all packages)
	for p in $(PACKAGES); do (cd $$p && uv run ruff check . && uv run ruff format --check . && uv run pyright) || exit 1; done

test:  ## pytest (all packages) + terraform fmt
	for p in $(PACKAGES); do (cd $$p && uv run pytest -q) || exit 1; done
	terraform fmt -check -recursive infra

run:  ## MCP server on :$(PORT) (fixture incidents unless NIGHTWATCH_TABLE is set)
	cd $(SERVER) && uv run uvicorn nightwatch.app:asgi --host 127.0.0.1 --port $(PORT)

inspect:  ## MCP Inspector against the local server
	@echo "Transport: Streamable HTTP   URL: $(MCP_URL)"
	npx -y @modelcontextprotocol/inspector

build:  ## Lambda zips (aarch64 manylinux wheels) -> dist/{mcp_server,pipeline,triage}.zip
	scripts/build_lambda.sh server mcp_server nightwatch
	scripts/build_lambda.sh pipeline pipeline nightwatch_pipeline
	scripts/build_lambda.sh pipeline triage nightwatch_pipeline triage
	scripts/build_demo.sh

deploy: build  ## build + terraform apply (envs/dev) + print the MCP URL
	terraform -chdir=$(TF_DEV) init -input=false
	terraform -chdir=$(TF_DEV) apply
	@echo "MCP URL: $$(terraform -chdir=$(TF_DEV) output -raw mcp_url)"

warm-on: build  ## OPTIONAL, not used: provisioned concurrency = 1 on the live alias (bills always-on; we warm by hand before recording)
	echo 'provisioned_concurrency = 1' > $(WARM_TFVARS)
	terraform -chdir=$(TF_DEV) init -input=false
	terraform -chdir=$(TF_DEV) apply

warm-off: build  ## OPTIONAL: provisioned concurrency = 0 (back to on-demand, no always-on cost)
	echo 'provisioned_concurrency = 0' > $(WARM_TFVARS)
	terraform -chdir=$(TF_DEV) init -input=false
	terraform -chdir=$(TF_DEV) apply

seed-household:  ## Write the demo household (Simi Valley, CAZ374), contact Priya, and escalation policy
	cd pipeline && $(AWS_ENV) uv run python -m nightwatch_pipeline.seed --table $$($(TF_OUT) table_name) \
		--contact-email "$$($(TF_OUT) contact_email)"

replay:  ## Replay one archived NWS alert through the bus: make replay FILE=~/nightwatch-alert-archive/archive/nws/<day>/<id>.json
	@test -n "$(FILE)" || (echo "usage: make replay FILE=<alert.json>"; exit 1)
	cd pipeline && $(AWS_ENV) uv run python -m nightwatch_pipeline.replay "$(FILE)" \
		--table $$($(TF_OUT) table_name) --bus $$($(TF_OUT) bus_name)

reset-incidents:  ## DEV ONLY: delete incidents, OPENKEYs, and signal records (keeps households); live alerts re-ingest within 5 min
	@test "$(CONFIRM)" = "yes" || (echo "usage: make reset-incidents CONFIRM=yes"; exit 1)
	cd pipeline && $(AWS_ENV) uv run python -m nightwatch_pipeline.cutover --table $$($(TF_OUT) table_name) --confirm

smoke:  ## Post-deploy smoke test: replay one alert end to end; fail on any builder/triage/notifier/escalation Lambda error
	$(AWS_ENV) scripts/smoke.sh $(FILE)

bad-deploy:  ## Deploy checkout-service with the latency regression (CodeDeploy, AllAtOnce); prints the deployment ID
	scripts/deploy_checkout.sh bad

good-deploy:  ## Deploy the good checkout-service version (this is the rollback)
	scripts/deploy_checkout.sh good

sim:  ## Simulated Alexa+ client (unofficial) on http://localhost:$(SIM_PORT), against the live MCP URL
	cd alexa-sim && MCP_URL="$$($(TF_OUT) mcp_url)" $(AWS_ENV) \
		uv run uvicorn nightwatch_sim.app:app --host 127.0.0.1 --port $(SIM_PORT)

sim-smoke:  ## Demo turns through the simulator agent against the live server (REAL notify + rollback)
	cd alexa-sim && MCP_URL="$$($(TF_OUT) mcp_url)" $(AWS_ENV) uv run python -m nightwatch_sim.smoke
