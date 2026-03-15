module "label" {
  source      = "./modules/label"
  name        = "scraper"
  environment = "dev"
  project     = "scraper-project"
  owner       = "Ben_TF"
}

########################################
# IAM Role for Lambda
########################################

resource "aws_iam_role" "lambda_role" {
  name = "scraper_lambda_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Effect = "Allow"
      }
    ]
  })
}

########################################
# Lambda IAM policy
########################################

resource "aws_iam_role_policy" "lambda_ec2_policy" {
  name = "lambda_ec2_launch"
  role = aws_iam_role.lambda_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ec2:RunInstances",
          "ec2:DescribeInstances",
          "iam:PassRole"
        ]
        Resource = "*"
      }
    ]
  })
}


########################################
# Lambda function
########################################
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/src/Lambda"
  output_path = "${path.module}/lambda.zip"
}


resource "aws_lambda_function" "scraper_launcher" {

  function_name = var.lambda_function_name

  role = aws_iam_role.lambda_role.arn

  handler = "lambda_function.lambda_handler"
  runtime = var.lambda_runtime

  filename = data.archive_file.lambda_zip.output_path

  environment {
    variables = {
      AMI_ID        = var.ami_id
      INSTANCE_TYPE = var.instance_type
      LOG_LEVEL     = var.lambda_log_level
    }
  }
  tags = module.label.tags
}

########################################
# EventBridge Schedule
########################################

resource "aws_cloudwatch_event_rule" "daily_scraper" {

  name = "daily-scraper-trigger"

  schedule_expression = "cron(0 13 ? * MON *)"

  tags = module.label.tags
}

########################################
# EventBridge Target (Lambda)
########################################

resource "aws_cloudwatch_event_target" "lambda_target" {

  rule = aws_cloudwatch_event_rule.daily_scraper.name

  target_id = "scraperLambda"

  arn = aws_lambda_function.scraper_launcher.arn

}

########################################
# Allow EventBridge to invoke Lambda
########################################

resource "aws_lambda_permission" "allow_eventbridge" {

  statement_id = "AllowExecutionFromEventBridge"

  action = "lambda:InvokeFunction"

  function_name = aws_lambda_function.scraper_launcher.function_name

  principal = "events.amazonaws.com"

  source_arn = aws_cloudwatch_event_rule.daily_scraper.arn

}

########################################
# EC2 IAM Role
########################################

resource "aws_iam_role" "ec2_role" {

  name = "scraper_ec2_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
        Effect = "Allow"
      }
    ]
  })
}

########################################
# EC2 IAM policy
########################################

resource "aws_iam_role_policy" "ec2_terminate_policy" {

  name = "ec2_self_terminate"

  role = aws_iam_role.ec2_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ec2:TerminateInstances",
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameter"
        ]
        Resource = "arn:aws:ssm:*:*:parameter/github_deploy_key"
      }
    ]
  })

}

########################################
# Instance Profile
########################################

resource "aws_iam_instance_profile" "ec2_profile" {

  name = "scraper_ec2_profile"

  role = aws_iam_role.ec2_role.name
  tags = module.label.tags
}

########################################
# Python scripts
########################################
resource "null_resource" "duckdb_export" {

  provisioner "local-exec" {
    command = "python3 duckdb_to_s3.py"
  }

  provisioner "local-exec" {
    when    = destroy
    command = "aws s3 rm s3://BDM060897/Products/ --recursive"
  }
}