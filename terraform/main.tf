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
  tags = module.label.tags
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
data "archive_file" "lambda_scraper_zip" {
  type        = "zip"
  source_file = "${path.module}/lambda/lambda_scraper.py"
  output_path = "${path.module}/lambda_scraper.zip"
}


resource "aws_lambda_function" "scraper_launcher" {

  function_name = var.lambda_function_name

  role = aws_iam_role.lambda_role_scraper.arn

  handler = "lambda_scraper.lambda_handler"
  runtime = var.lambda_runtime

  filename         = data.archive_file.lambda_scraper_zip.output_path
  source_code_hash = filebase64sha256(data.archive_file.lambda_scraper_zip.output_path)

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

  schedule_expression = "cron(0 13 ? * TUE *)"

  tags = module.label.tags
}

#-------------------------------
# EventBridge Target (Lambda)
#-------------------------------

resource "aws_cloudwatch_event_target" "lambda_target_scraper" {

  rule = aws_cloudwatch_event_rule.daily_scraper.name

  target_id = "scraperLambda"

  arn = aws_lambda_function.scraper_launcher.arn

}

#-------------------------------
# Allow EventBridge to invoke Lambda
#-------------------------------

resource "aws_lambda_permission" "allow_eventbridge_scraper" {

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
  tags = module.label.tags
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
          "s3:PutObject"
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


  depends_on = [aws_iam_role.ec2_role]

  lifecycle {
    create_before_destroy = false
  }

  tags = module.label.tags
}

#####################################
# ATHENA
#####################################

# ----------------------------
# Glue Catalog Database
# ----------------------------
resource "aws_glue_catalog_database" "products_db" {
  name = "products_db"
  tags = module.label.tags
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
      name = "image"
      type = "string"
    }

    columns {
      name = "price"
      type = "double"
    }

    columns {
      name = "pricewithoutdiscount"
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
    type = "date"
  }

  partition_keys {
    name = "store"
    type = "string"
  }

  partition_keys {
    name = "catid"
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
  tags = module.label.tags
}

resource "aws_iam_role_policy" "lambda_policy" {
  name = "athena_lambda_policy"
  role = aws_iam_role.lambda_role_athena.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "athena:StartQueryExecution",
          "athena:GetQueryExecution",
          "athena:GetQueryResults",
          "s3:GetBucketLocation"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket",
          "s3:PutObject",
          "s3:DeleteObject"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "glue:GetDatabase",
          "glue:GetDatabases",
          "glue:GetTable",
          "glue:GetTables",
          "glue:GetPartition",
          "glue:GetPartitions",
          "glue:CreateTable",
          "glue:DeleteTable",
          "glue:BatchCreatePartition", #keep or msck doesnt work
          "glue:DeletePartition",
          "glue:BatchDeletePartition"
        ]
        Resource = "*"
      }
    ]
  })
}

# ----------------------------
# Athena lambda function
# ----------------------------
data "archive_file" "lambda_prepare_zip" {
  type        = "zip"
  source_file = "${path.module}/lambda/lambda_prepare.py"
  output_path = "${path.module}/lambda_prepare.zip"
}

resource "aws_lambda_function" "athena_prepare_tables" {
  function_name = "athena-prepare-tables"
  role          = aws_iam_role.lambda_role_athena.arn
  handler       = "lambda_prepare.lambda_handler"
  runtime       = "python3.11"
  timeout       = 300

  filename         = data.archive_file.lambda_prepare_zip.output_path
  source_code_hash = filebase64sha256(data.archive_file.lambda_prepare_zip.output_path)

  environment {
    variables = {
      DATABASE        = "products_db"
      OUTPUT_LOCATION = "s3://bdm060897-prod/scraper/athena-results/"
    }
  }

  tags = module.label.tags
}

# ----------------------------
# history lambda functions
# ----------------------------

#layer: zip folder that has python
data "archive_file" "history_layer_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/layer_src"
  output_path = "${path.module}/history_layer.zip"
}

resource "aws_s3_object" "history_layer_zip" {
  bucket = "bdm060897-prod"
  key    = "lambda-layers/history_layer.zip"
  source = data.archive_file.history_layer_zip.output_path
  etag   = filemd5(data.archive_file.history_layer_zip.output_path)
}

resource "aws_lambda_layer_version" "history_layer" {
  layer_name          = "history-layer"
  compatible_runtimes = ["python3.11"]
  s3_bucket           = aws_s3_object.history_layer_zip.bucket
  s3_key              = aws_s3_object.history_layer_zip.key
  source_code_hash    = filebase64sha256(data.archive_file.history_layer_zip.output_path)
}

data "archive_file" "avg_deals_30d_history_zip" {
  type        = "zip"
  source_file = "${path.module}/lambda/avg_deals_30d_history.py"
  output_path = "${path.module}/avg_deals_30d_history.zip"
}

resource "aws_lambda_function" "avg_deals_30d_history" {
  function_name = "avg-deals-30d-history"
  role          = aws_iam_role.lambda_role_athena.arn
  handler       = "avg_deals_30d_history.lambda_handler"
  runtime       = "python3.11"
  timeout       = 300

  layers = [aws_lambda_layer_version.history_layer.arn]

  filename         = data.archive_file.avg_deals_30d_history_zip.output_path
  source_code_hash = filebase64sha256(data.archive_file.avg_deals_30d_history_zip.output_path)
  tags = module.label.tags
}

data "archive_file" "discounts_history_zip" {
  type        = "zip"
  source_file = "${path.module}/lambda/discounts_history.py"
  output_path = "${path.module}/discounts_history.zip"
}

resource "aws_lambda_function" "discounts_history" {
  function_name = "discounts-history"
  role          = aws_iam_role.lambda_role_athena.arn
  handler       = "discounts_history.lambda_handler"
  runtime       = "python3.11"
  timeout       = 300

  layers = [aws_lambda_layer_version.history_layer.arn]

  filename         = data.archive_file.discounts_history_zip.output_path
  source_code_hash = filebase64sha256(data.archive_file.discounts_history_zip.output_path)
  tags = module.label.tags
}

data "archive_file" "list_price_increases_history_zip" {
  type        = "zip"
  source_file = "${path.module}/lambda/list_price_increases_history.py"
  output_path = "${path.module}/list_price_increases_history.zip"
}

resource "aws_lambda_function" "list_price_increases_history" {
  function_name = "list_price_increases-history"
  role          = aws_iam_role.lambda_role_athena.arn
  handler       = "list_price_increases_history.lambda_handler"
  runtime       = "python3.11"
  timeout       = 300

  layers = [aws_lambda_layer_version.history_layer.arn]

  filename         = data.archive_file.list_price_increases_history_zip.output_path
  source_code_hash = filebase64sha256(data.archive_file.list_price_increases_history_zip.output_path)
  tags = module.label.tags
}

data "archive_file" "list_price_descreases_history_zip" {
  type        = "zip"
  source_file = "${path.module}/lambda/list_price_descreases_history.py"
  output_path = "${path.module}/list_price_descreases_history.zip"
}

resource "aws_lambda_function" "list_price_descreases_history" {
  function_name = "list_price_descreases-history"
  role          = aws_iam_role.lambda_role_athena.arn
  handler       = "list_price_descreases_history.lambda_handler"
  runtime       = "python3.11"
  timeout       = 300

  layers = [aws_lambda_layer_version.history_layer.arn]

  filename         = data.archive_file.list_price_descreases_history_zip.output_path
  source_code_hash = filebase64sha256(data.archive_file.list_price_descreases_history_zip.output_path)
  tags = module.label.tags
}

# ----------------------------
# Dashboard lambda functions
# ----------------------------
data "archive_file" "dashboard_aws_zip" {
  type        = "zip"
  source_file = "${path.module}/lambda/dashboard_aws.py"
  output_path = "${path.module}/dashboard_aws.zip"
}

resource "aws_lambda_function" "dashboard_aws" {
  function_name = "dashboard-aws"
  role          = aws_iam_role.lambda_role_athena.arn
  handler       = "dashboard_aws.lambda_handler"
  runtime       = "python3.11"
  timeout       = 300
  memory_size   = 512

  layers           = [aws_lambda_layer_version.history_layer.arn]
  filename         = data.archive_file.dashboard_aws_zip.output_path
  source_code_hash = filebase64sha256(data.archive_file.dashboard_aws_zip.output_path)

  environment {
    variables = {
      BUCKET         = "bdm060897-prod"
      RESULTS_PREFIX = "scraper/athena-results"
      DASHBOARD_KEY  = "scraper/dashboard/dashboard.html"
    }
  }
  tags = module.label.tags
}
# ----------------------------
# s3 EventBridge rule
# ----------------------------

resource "aws_s3_bucket_notification" "bucket_notifications" {
  bucket      = "bdm060897-prod"
  eventbridge = true
}

resource "aws_cloudwatch_event_rule" "s3_success" {
  name = "trigger-step-function-on-scraper-success"

  event_pattern = jsonencode({
    source      = ["aws.s3"],
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
  tags = module.label.tags
}

resource "aws_cloudwatch_event_target" "target_step_function" {
  rule      = aws_cloudwatch_event_rule.s3_success.name
  target_id = "target-step-function"
  arn       = aws_sfn_state_machine.scraper_dashboard_state_machine.arn
  role_arn  = aws_iam_role.eventbridge_invoke_step_function_role.arn
}

resource "aws_iam_role" "eventbridge_invoke_step_function_role" {
  name = "eventbridge-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "events.amazonaws.com"
      }
    }]
  })
  tags = module.label.tags
}

resource "aws_iam_role_policy" "eventbridge_policy" {
  name = "eventbridge-policy"
  role = aws_iam_role.eventbridge_invoke_step_function_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "states:StartExecution"
        ]
        Resource = aws_sfn_state_machine.scraper_dashboard_state_machine.arn
      }
    ]
  })
}

# ----------------------------
# Step Function
# ----------------------------

resource "aws_iam_role" "scraper_dashboard_step_function_role" {
  name = "scraper-dashboard-step-function-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "states.amazonaws.com"
      }
    }]
  })
  tags = module.label.tags
}

resource "aws_iam_role_policy" "scraper_dashboard_step_function_policy" {
  name = "scraper-dashboard-step-function-policy"
  role = aws_iam_role.scraper_dashboard_step_function_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "athena:StartQueryExecution",
          "athena:GetQueryExecution",
          "athena:GetQueryResults",
          "s3:GetBucketLocation",
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket",
          "glue:GetDatabase",
          "glue:GetDatabases",
          "glue:GetTable",
          "glue:GetTables",
          "glue:GetPartition",
          "glue:GetPartitions",
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = [
          aws_lambda_function.athena_prepare_tables.arn,
          aws_lambda_function.avg_deals_30d_history.arn,
          aws_lambda_function.discounts_history.arn,
          aws_lambda_function.list_price_increases_history.arn,
          aws_lambda_function.list_price_descreases_history.arn,
          aws_lambda_function.dashboard_aws.arn
        ]
      }
    ]
  })
}


resource "aws_sfn_state_machine" "scraper_dashboard_state_machine" {
  name     = "scraper-dashboard-state-machine"
  role_arn = aws_iam_role.scraper_dashboard_step_function_role.arn

  definition = jsonencode({
    Comment = "Prepare tables and output dashboard data",
    StartAt = "lambda_prepare",
    States = {
      lambda_prepare = {
        Type     = "Task",
        Resource = aws_lambda_function.athena_prepare_tables.arn,
        Next     = "run_queries_in_parallel"
      },
      run_queries_in_parallel = {
        Type = "Parallel",
        Next = "dashboard_lambda",

        Branches = [
          {
            StartAt = "list_price_increases",
            States = {
              list_price_increases = {
                Type     = "Task",
                Resource = "arn:aws:states:::athena:startQueryExecution.sync"
                Parameters = {
                  QueryString           = file("${path.module}/lambda/sql/list_price_increases.sql")
                  QueryExecutionContext = { Database = "products_db" }
                  ResultConfiguration   = { OutputLocation = "s3://bdm060897-prod/scraper/athena-results/list_price_increases/" }
                }
                Next = "list_price_increases_history"
              },
              list_price_increases_history = {
                Type     = "Task",
                Resource = aws_lambda_function.list_price_increases_history.arn
                End      = true
              }
            }
          },
          {
            StartAt = "list_price_decreases",
            States = {
              list_price_decreases = {
                Type     = "Task",
                Resource = "arn:aws:states:::athena:startQueryExecution.sync"
                Parameters = {
                  QueryString           = file("${path.module}/lambda/sql/list_price_decreases.sql")
                  QueryExecutionContext = { Database = "products_db" }
                  ResultConfiguration   = { OutputLocation = "s3://bdm060897-prod/scraper/athena-results/list_price_decreases/" }
                }
                Next = "list_price_descreases_history"
              },
              list_price_descreases_history = {
                Type     = "Task",
                Resource = aws_lambda_function.list_price_descreases_history.arn
                End      = true
              }
            }
          },
          {
            StartAt = "discounts",
            States = {
              discounts = {
                Type     = "Task",
                Resource = "arn:aws:states:::athena:startQueryExecution.sync"
                Parameters = {
                  QueryString           = file("${path.module}/lambda/sql/discounts.sql")
                  QueryExecutionContext = { Database = "products_db" }
                  ResultConfiguration   = { OutputLocation = "s3://bdm060897-prod/scraper/athena-results/discounts/" }
                }
                Next = "discounts_history"
              },
              discounts_history = {
                Type     = "Task",
                Resource = aws_lambda_function.discounts_history.arn
                End      = true
              }
            }
          },
          {
            StartAt = "avg_deals_30d",
            States = {
              avg_deals_30d = {
                Type     = "Task",
                Resource = "arn:aws:states:::athena:startQueryExecution.sync"
                Parameters = {
                  QueryString           = file("${path.module}/lambda/sql/avg_deals_30d.sql")
                  QueryExecutionContext = { Database = "products_db" }
                  ResultConfiguration   = { OutputLocation = "s3://bdm060897-prod/scraper/athena-results/avg_deals_30d/" }
                }
                Next = "avg_deals_30d_history"
              },
              avg_deals_30d_history = {
                Type     = "Task",
                Resource = aws_lambda_function.avg_deals_30d_history.arn
                End      = true
              }
            }
          }
        ],
      },
      dashboard_lambda = {
        Type     = "Task",
        Resource = aws_lambda_function.dashboard_aws.arn
        End      = true
      }
    }
  })
  tags = module.label.tags
}





