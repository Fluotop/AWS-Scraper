########################################
# Variables
########################################

variable "region" {
  description = "AWS region"
  type        = string
}

variable "environment" {
  description = "Deployment environment (e.g., dev, prod)"
  type        = string
}

variable "owner" {
  description = "Owner of the resources"
  type        = string
}

variable "project" {
  description = "Project name"
  type        = string
}

#ec2
variable "ami_id" {
  description = "AMI used for scraper instance"
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
}

#lambda
variable "lambda_function_name" {
  description = "Name of the Lambda function"
  type        = string
}

variable "lambda_runtime" {
  description = "Runtime for the Lambda function"
  type        = string
}
variable "lambda_log_level" {
  description = "Log level for Lambda function"
  type        = string
}