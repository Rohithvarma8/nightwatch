output "topic_arn" {
  description = "SNS fan-out topic for notifications."
  value       = aws_sns_topic.notify.arn
}

output "function_name" {
  description = "Notifier Lambda."
  value       = aws_lambda_function.this.function_name
}
