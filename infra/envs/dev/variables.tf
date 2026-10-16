variable "provisioned_concurrency" {
  description = "Provisioned concurrency for the MCP server. 0 = off; set to 1 to remove cold starts (always-on cost)."
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
