module "label" {
  source      = "./modules/label"
  name        = "scraper"
  environment = "dev"
  project     = "scraper-project"
  owner       = "Ben_TF"
}

#####################################
# SCRAPER
#####################################

#-------------------------------
# IAM Role for Lambda
#-------------------------------

resource "aws_iam_role" "lambda_role_scraper" {
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

#-------------------------------
# Lambda IAM policy
#-------------------------------

resource "aws_iam_role_policy" "lambda_ec2_policy" {
  name = "lambda_ec2_launch"
  role = aws_iam_role.lambda_role_scraper.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ec2:RunInstances",
          "ec2:DescribeInstances",
          "iam:PassRole",
          "ec2:CreateTags"
        ]
        Resource = "*"
      }
    ]
  })
}


#-------------------------------
# Lambda function
#-------------------------------
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda"
  output_path = "${path.module}/lambda.zip"
}


resource "aws_lambda_function" "scraper_launcher" {

  function_name = var.lambda_function_name

  role = aws_iam_role.lambda_role_scraper.arn

  handler = "lambda.lambda_handler"
  runtime = var.lambda_runtime

  filename = data.archive_file.lambda_zip.output_path
  source_code_hash = filebase64sha256("lambda.zip")

  environment {
    variables = {
      AMI_ID        = var.ami_id
      INSTANCE_TYPE = var.instance_type
      LOG_LEVEL     = var.lambda_log_level
    }
  }
  tags = module.label.tags
}

#-------------------------------
# EventBridge Schedule
#-------------------------------

resource "aws_cloudwatch_event_rule" "daily_scraper" {

  name = "daily-scraper-trigger"

  schedule_expression = "cron(0 13 ? * MON *)"

  tags = module.label.tags
}

#-------------------------------
# EventBridge Target (Lambda)
#-------------------------------

resource "aws_cloudwatch_event_target" "lambda_target" {

  rule = aws_cloudwatch_event_rule.daily_scraper.name

  target_id = "scraperLambda"

  arn = aws_lambda_function.scraper_launcher.arn

}

#-------------------------------
# Allow EventBridge to invoke Lambda
#-------------------------------

resource "aws_lambda_permission" "allow_eventbridge" {

  statement_id = "AllowExecutionFromEventBridge"

  action = "lambda:InvokeFunction"

  function_name = aws_lambda_function.scraper_launcher.function_name

  principal = "events.amazonaws.com"

  source_arn = aws_cloudwatch_event_rule.daily_scraper.arn

}

#-------------------------------
# EC2 IAM Role
#-------------------------------

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

#-------------------------------
# EC2 IAM policy
#-------------------------------

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
      },
      {
        Effect = "Allow"
        Action = [
          "s3:putObject"
        ]
        Resource = "arn:aws:s3:::bdm060897-prod/*"
      }
    ]
  })

}

#-------------------------------
# Instance Profile
#-------------------------------

resource "aws_iam_instance_profile" "ec2_profile" {

  name = "scraper_ec2_profile"

  role = aws_iam_role.ec2_role.name
  tags = module.label.tags
}

#####################################
# ATHENA
#####################################

# ----------------------------
# S3 bucket for Athena results
# ----------------------------
resource "aws_s3_bucket" "athena_results" {
  bucket = "bdm060897-prod"
}

# ----------------------------
# Glue Catalog Database
# ----------------------------
resource "aws_glue_catalog_database" "products_db" {
  name = "products_db"
}

# ----------------------------
# Glue Catalog Table (Athena)
# ----------------------------
resource "aws_glue_catalog_table" "products" {
  name          = "products"
  database_name = aws_glue_catalog_database.products_db.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "classification" = "parquet"
  }

  storage_descriptor {
    location      = "s3://bdm060897-prod/scraper/products/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "product_id"
      type = "string"
    }

    columns {
      name = "name"
      type = "string"
    }

    columns {
      name = "brand"
      type = "string"
    }

    columns {
      name = "maincat"
      type = "string"
    }

    columns {
      name = "cat"
      type = "string"
    }

    columns {
      name = "subcat"
      type = "string"
    }

    columns {
      name = "catid"
      type = "string"
    }

    columns {
      name = "image"
      type = "string"
    }

    columns {
      name = "price"
      type = "double"
    }

    columns {
      name = "priceWithoutDiscount"
      type = "double"
    }

    columns {
      name = "list_price"
      type = "double"
    }

    columns {
      name = "is_available"
      type = "boolean"
    }

    columns {
      name = "link"
      type = "string"
    }
  }

  
  partition_keys {
    name = "scrape_date"
    type = "string"
  }

  partition_keys {
    name = "store"
    type = "string"
  }
}

# ----------------------------
# Athena lambda IAM Role
# ----------------------------

resource "aws_iam_role" "lambda_role_athena" {
  name = "athena_lambda_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy" "lambda_policy" {
  name = "athena_lambda_policy"
  role = aws_iam_role.lambda_role_athena.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # Athena permissions
      {
        Effect = "Allow"
        Action = [
          "athena:StartQueryExecution",
          "athena:GetQueryExecution",
          "athena:GetQueryResults"
        ]
        Resource = "*"
      },
      # S3 access (data + results)
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket",
          "s3:PutObject"
        ]
        Resource = "*"
      },
      # Logs
      {
        Effect = "Allow"
        Action = [
          "logs:*"
        ]
        Resource = "*"
      }
    ]
  })
}

# ----------------------------
# Athena lambda function
# ----------------------------

resource "aws_lambda_function" "athena_runner" {
  function_name = "athena-query-runner"
  role          = aws_iam_role.lambda_role.arn
  handler       = "index.handler"
  runtime       = "python3.11"

  filename         = "lambda_athena.zip" # zip your code
  source_code_hash = filebase64sha256("lambda_athena.zip")

  environment {
    variables = {
      DATABASE        = "products_db"
      OUTPUT_LOCATION = "s3://bdm060897-prod/scraper/athena-results/"
    }
  }
}

# ----------------------------
# s3 EventBridge rule
# ----------------------------
resource "aws_cloudwatch_event_rule" "s3_success" {
  name = "trigger-athena-on-scraper-success"

  event_pattern = jsonencode({
    source = ["aws.s3"],
    detail-type = ["Object Created"],
    detail = {
      bucket = {
        name = ["bdm060897-prod"]
      },
      object = {
        key = [{
          prefix = "scraper/products/_SUCCESS"
        }]
      }
    }
  })
}

resource "aws_cloudwatch_event_target" "lambda_target" {
  rule      = aws_cloudwatch_event_rule.s3_success.name
  target_id = "athena-lambda"
  arn       = aws_lambda_function.athena_runner.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.athena_runner.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.s3_success.arn
}