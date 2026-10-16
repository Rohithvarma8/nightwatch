output "mcp_url" {
  description = "MCP endpoint for Inspector / alexa-ai."
  value       = module.mcp_server.mcp_url
}

output "healthz_url" {
  description = "Health check."
  value       = "${module.mcp_server.api_endpoint}/healthz"
}

output "table_name" {
  description = "DynamoDB table (used by make seed-household / make replay)."
  value       = module.data.table_name
}

output "bus_name" {
  description = "EventBridge bus (used by make replay)."
  value       = module.ingest.bus_name
}
