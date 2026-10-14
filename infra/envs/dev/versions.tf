terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.68.0"
    }
  }

  backend "s3" {
    bucket       = "nightwatch-tfstate-946509368103"
    key          = "envs/dev/terraform.tfstate"
    region       = "us-west-2"
    profile      = "nightwatch"
    use_lockfile = true
    encrypt      = true
  }
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
