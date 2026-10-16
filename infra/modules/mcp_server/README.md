# mcp_server

The Night Watch MCP server on Lambda (Python 3.12, arm64) with uvicorn behind the
[AWS Lambda Web Adapter](https://github.com/awslabs/aws-lambda-web-adapter) layer, exposed by an
API Gateway HTTP API (`$default` stage, routes `ANY /mcp` and `GET /healthz`, no authorizers).

- Lambda Web Adapter waits for `GET /healthz` before it sends traffic.
- `MCP_ALLOWED_HOSTS` is set to the execute-api domain. Without it, the SDK's DNS-rebinding
  protection answers every request with 421.
- API Gateway invokes the `live` alias. To turn on provisioned concurrency later, set
  `provisioned_concurrency > 0` (it bills around the clock).
- The IAM role can write CloudWatch Logs and read the table: `GetItem` + `Query` on the table and GSI1. Nothing else.
- No VPC.

| Input | Default | |
|---|---|---|
| `zip_path` | (required) | `dist/mcp_server.zip` from `make build` |
| `table_name` / `table_arn` | (required) | from `modules/data` |
| `household_id` | `hh_demo` | |
| `memory_size` / `timeout` | 512 / 15 | |
| `provisioned_concurrency` | 0 | |
| `log_retention_days` | 7 | |
| `throttle_rate_limit` / `throttle_burst_limit` | 20 / 50 | cost guard |

Outputs: `mcp_url`, `api_endpoint`, `function_name`, `log_group`.
