variable "provisioned_concurrency" {
  description = "Optional provisioned concurrency for the MCP server. Not used (0): we warm by hand before recording. 1 removes cold starts but bills always-on."
  type        = number
  default     = 0
}

variable "household_ids" {
  description = "Households the pipeline ingests for. The first is the one the MCP tools read."
  type        = list(string)
  default     = ["hh_demo"]
}

variable "nws_user_agent" {
  description = "User-Agent for api.weather.gov: \"(app-name, contact@email)\". Set in terraform.tfvars (gitignored)."
  type        = string
  sensitive   = true
}

variable "triage_model_id" {
  description = "Primary Bedrock model for the triage agent."
  type        = string
  default     = "amazon.nova-lite-v1:0"
}

variable "triage_fallback_model_id" {
  description = "Fallback Bedrock model. Claude Haiku 4.5 profile; switch to us.anthropic.claude-haiku-5-5 once this account has access."
  type        = string
  default     = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
}
