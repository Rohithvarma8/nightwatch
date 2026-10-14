terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Bootstrap keeps its own state locally; it creates the bucket every other stack uses.
}

provider "aws" {
  region              = "us-west-2"
  profile             = "nightwatch"
  allowed_account_ids = ["946509368103"]

  default_tags {
    tags = {
      project = "nightwatch"
    }
  }
}
