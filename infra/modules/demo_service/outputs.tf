output "service_name" {
  description = "Demo service name."
  value       = var.service_name
}

output "checkout_url" {
  description = "checkout-service endpoint."
  value       = "${aws_apigatewayv2_api.checkout.api_endpoint}/checkout"
}

output "codedeploy_app" {
  description = "CodeDeploy application."
  value       = aws_codedeploy_app.checkout.name
}

output "codedeploy_group" {
  description = "CodeDeploy deployment group."
  value       = aws_codedeploy_deployment_group.checkout.deployment_group_name
}

output "deployment_group_arn" {
  description = "Deployment group ARN (for IAM)."
  value       = "arn:aws:codedeploy:${local.region}:${local.account}:deploymentgroup:${aws_codedeploy_app.checkout.name}/${aws_codedeploy_deployment_group.checkout.deployment_group_name}"
}

output "codedeploy_app_arn" {
  description = "CodeDeploy application ARN (for IAM)."
  value       = "arn:aws:codedeploy:${local.region}:${local.account}:application:${aws_codedeploy_app.checkout.name}"
}

output "alarm_name" {
  description = "p95 latency alarm."
  value       = aws_cloudwatch_metric_alarm.latency.alarm_name
}
