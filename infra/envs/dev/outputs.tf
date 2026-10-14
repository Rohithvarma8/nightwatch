output "mcp_url" {
  description = "MCP endpoint for Inspector / alexa-ai."
  value       = module.mcp_server.mcp_url
}

output "healthz_url" {
  description = "Health check."
  value       = "${module.mcp_server.api_endpoint}/healthz"
}
