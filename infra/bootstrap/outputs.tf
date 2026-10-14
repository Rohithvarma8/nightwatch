output "state_bucket_name" {
  description = "S3 bucket for Terraform remote state (use with use_lockfile = true)."
  value       = aws_s3_bucket.tfstate.bucket
}
