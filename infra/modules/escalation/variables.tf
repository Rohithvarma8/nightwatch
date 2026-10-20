variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
  default     = "nightwatch"
}

variable "zip_path" {
  description = "Path to dist/pipeline.zip."
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

variable "notify_topic_arn" {
  description = "SNS topic the escalation notification goes to."
  type        = string
}

variable "log_retention_days" {
  description = "CloudWatch log retention."
  type        = number
  default     = 7
}
