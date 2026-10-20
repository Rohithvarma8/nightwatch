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

output "contact_email" {
  description = "Demo contact email for make seed-household."
  value       = var.contact_email
  sensitive   = true
}

output "notify_topic_arn" {
  description = "SNS notification topic."
  value       = module.notify.topic_arn
}

output "checkout_url" {
  description = "Demo checkout-service endpoint."
  value       = module.demo_service.checkout_url
}

output "codedeploy_app" {
  description = "CodeDeploy application (make bad-deploy / good-deploy)."
  value       = module.demo_service.codedeploy_app
}

output "codedeploy_group" {
  description = "CodeDeploy deployment group."
  value       = module.demo_service.codedeploy_group
}

output "checkout_alarm" {
  description = "p95 latency alarm name."
  value       = module.demo_service.alarm_name
}
