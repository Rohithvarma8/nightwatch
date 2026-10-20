output "function_arn" {
  description = "Escalation Lambda (target of one-time schedules)."
  value       = aws_lambda_function.this.arn
}

output "function_name" {
  description = "Escalation Lambda name."
  value       = aws_lambda_function.this.function_name
}

output "scheduler_role_arn" {
  description = "Role Scheduler assumes to invoke the escalation Lambda (passed by the builder)."
  value       = aws_iam_role.scheduler.arn
}
