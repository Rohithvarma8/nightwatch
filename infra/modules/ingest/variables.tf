variable "name_prefix" {
  description = "Prefix for function, role, and schedule names."
  type        = string
  default     = "nightwatch"
}

variable "zip_path" {
  description = "Path to dist/pipeline.zip from `make build`."
  type        = string
}

variable "table_name" {
  description = "DynamoDB table name."
  type        = string
}

variable "table_arn" {
  description = "DynamoDB table ARN."
  type        = string
}

variable "household_ids" {
  description = "Households to ingest for (each needs a PROFILE item; see `make seed-household`)."
  type        = list(string)
}

variable "nws_user_agent" {
  description = "User-Agent for api.weather.gov, e.g. \"(app-name, contact@email)\". Set in gitignored terraform.tfvars."
  type        = string
  sensitive   = true
}

variable "nws_schedule" {
  description = "How often the NWS ingester runs (also the expiry sweep)."
  type        = string
  default     = "rate(5 minutes)"
}

variable "escalation_target_arn" {
  description = "Escalation Lambda the builder's one-time schedules invoke."
  type        = string
}

variable "escalation_scheduler_role_arn" {
  description = "Role passed to Scheduler for escalation schedules."
  type        = string
}

variable "log_retention_days" {
  description = "CloudWatch log retention."
  type        = number
  default     = 7
}
