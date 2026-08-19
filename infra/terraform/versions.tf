terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.40, < 7.0"
    }
  }

  # Configure remote state before applying in production. Local state for an
  # account that holds the secrets CMK policy is a single laptop away from an
  # outage. Example:
  #
  # backend "s3" {
  #   bucket         = "webforx-tfstate"
  #   key            = "controlhub/zero-trust/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "webforx-tflock"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Application = "controlhub"
      ManagedBy   = "terraform"
      Component   = "zero-trust-phase5"
    }
  }
}
