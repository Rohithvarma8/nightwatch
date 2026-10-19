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

variable "ntfy_topic" {
  description = "ntfy.sh topic for push (anyone who knows it can read it: keep it unguessable). Stored as an SSM SecureString."
  type        = string
  sensitive   = true
}

variable "ses_sender_email" {
  description = "SES sender (verified identity). In the SES sandbox, recipients must be verified too."
  type        = string
  sensitive   = true
}

variable "log_retention_days" {
  description = "CloudWatch log retention."
  type        = number
  default     = 7
}
