variable "provisioned_concurrency" {
  description = "Provisioned concurrency for the MCP server. 0 = off; set to 1 to remove cold starts (always-on cost)."
  type        = number
  default     = 0
}
