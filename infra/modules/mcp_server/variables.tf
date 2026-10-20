variable "name" {
  description = "Function and API name."
  type        = string
  default     = "nightwatch-mcp"
}

variable "zip_path" {
  description = "Path to the Lambda zip built by `make build` (dist/mcp_server.zip)."
  type        = string
}

variable "lambda_web_adapter_layer_arn" {
  description = "AWS Lambda Web Adapter layer (arm64). From the awslabs/aws-lambda-web-adapter README, v1.1.0."
  type        = string
  default     = "arn:aws:lambda:us-west-2:753240598075:layer:LambdaAdapterLayerArm64:30"
}

variable "memory_size" {
  description = "Lambda memory in MB."
  type        = number
  default     = 512
}

variable "timeout" {
  description = "Lambda timeout in seconds."
  type        = number
  default     = 15
}

variable "provisioned_concurrency" {
  description = "Provisioned concurrency on the `live` alias. 0 disables it (no always-on cost)."
  type        = number
  default     = 0
}

variable "log_retention_days" {
  description = "CloudWatch log retention for the function."
  type        = number
  default     = 7
}

variable "throttle_rate_limit" {
  description = "API Gateway steady-state requests per second (cost guard for a public, unauthenticated endpoint)."
  type        = number
  default     = 20
}

variable "throttle_burst_limit" {
  description = "API Gateway burst limit."
  type        = number
  default     = 50
}

variable "table_name" {
  description = "DynamoDB table the tools read (NIGHTWATCH_TABLE)."
  type        = string
}

variable "table_arn" {
  description = "DynamoDB table ARN (read-only access is granted on it and its GSI1)."
  type        = string
}

variable "notify_topic_arn" {
  description = "SNS topic notify_contact / escalate publish to (the only non-DynamoDB call)."
  type        = string
}

variable "rollback" {
  description = "rollback_deploy target: CodeDeploy app/group names and ARNs. null disables it."
  type = object({
    app                  = string
    group                = string
    app_arn              = string
    deployment_group_arn = string
  })
  default = null
}

variable "household_id" {
  description = "Household the tools read (single demo household until account linking)."
  type        = string
  default     = "hh_demo"
}
