variable "name" {
  description = "Triage Lambda name."
  type        = string
  default     = "nightwatch-triage"
}

variable "zip_path" {
  description = "Path to dist/triage.zip from `make build` (pipeline + Strands)."
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

variable "bus_name" {
  description = "EventBridge bus carrying IncidentChanged events."
  type        = string
}

variable "model_id" {
  description = "Primary Bedrock model (on-demand model ID or inference profile ID)."
  type        = string
}

variable "fallback_model_id" {
  description = "Fallback Bedrock model, tried inside the same 8 s budget. Empty to disable."
  type        = string
  default     = ""
}

variable "log_retention_days" {
  description = "CloudWatch log retention."
  type        = number
  default     = 7
}
