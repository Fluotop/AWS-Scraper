output "tags" {
  description = "Standard resource tags"
  value       = local.tags
}

output "name" {
  description = "Standardized resource name"
  value       = "${var.name}-${var.environment}"
}