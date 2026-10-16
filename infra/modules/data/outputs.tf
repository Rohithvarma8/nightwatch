output "table_name" {
  description = "DynamoDB table name."
  value       = aws_dynamodb_table.this.name
}

output "table_arn" {
  description = "DynamoDB table ARN."
  value       = aws_dynamodb_table.this.arn
}

output "gsi1_arn" {
  description = "ARN of the active-incidents index."
  value       = "${aws_dynamodb_table.this.arn}/index/GSI1"
}
