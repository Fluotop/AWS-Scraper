locals {
  tags = {
    Name        = var.name
    Owner       = var.owner
    Environment = var.environment
    Project   = var.project
    ManagedBy   = "Terraform"
  }
}