output "function_name" {
  description = "Triage Lambda."
  value       = aws_lambda_function.this.function_name
}

output "model_arns" {
  description = "Bedrock ARNs the triage role may invoke."
  value       = local.model_arns
}
