# Production environment variables
region      = "us-east-1"
environment = "prod"
owner       = "Ben_TF"
project     = "Scraper_Project"

ami_id        = "ami-0f3caa1cf4417e51b"
instance_type = "t3.micro"

lambda_function_name = "scraper-launcher"
lambda_runtime       = "python3.11"
lambda_log_level     = "info"

bucket_name        = "bdm060897-prod"
domain_name        = "bendemaesschalck.be"
certificate_domain = "bendemaesschalck.be"