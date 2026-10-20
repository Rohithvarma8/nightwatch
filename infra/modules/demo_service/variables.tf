variable "service_name" {
  description = "Demo prod service (Lambda function name and CodeDeploy group)."
  type        = string
  default     = "checkout-service"
}

variable "checkout_zip_path" {
  description = "dist/checkout.zip."
  type        = string
}

variable "loadgen_zip_path" {
  description = "dist/loadgen.zip."
  type        = string
}

variable "loadgen_enabled" {
  description = "Run the load generator (1 run/min, ~20 requests). Turn off after recording."
  type        = bool
  default     = true
}

variable "latency_threshold_ms" {
  description = "p95 Duration alarm threshold."
  type        = number
  default     = 500
}

variable "log_retention_days" {
  description = "CloudWatch log retention."
  type        = number
  default     = 7
}
