terraform {
  required_version = ">= 1.10, < 2.0"
  backend "s3" {}
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = {
      project             = "issue-classification-pipeline"
      environment         = "dev"
      owner               = var.owner
      cost-center         = "learning"
      managed-by          = "terraform"
      data-classification = "synthetic"
    }
  }
}

variable "region" { type = string }
variable "owner" { type = string }
variable "model_id" { type = string }
variable "model_resource_arns" {
  type        = list(string)
  description = "Reviewed model and inference-profile ARNs; never an unrestricted wildcard."
  validation {
    condition     = length(var.model_resource_arns) > 0 && alltrue([for arn in var.model_resource_arns : startswith(arn, "arn:") && !strcontains(arn, "*")])
    error_message = "Provide explicit model resources without wildcards."
  }
}
variable "artifact_bucket_name" { type = string }
variable "lambda_zip" {
  type    = string
  default = "../../../dist/lambda.zip"
}
variable "permissions_boundary_arn" {
  type        = string
  description = "Pre-approved IAM boundary for the runtime role; required, not an empty placeholder."
  validation {
    condition     = startswith(var.permissions_boundary_arn, "arn:")
    error_message = "Configure an approved IAM permissions boundary before planning."
  }
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

resource "aws_cloudwatch_log_group" "sut" {
  name              = "/aws/lambda/issue-classifier-dev"
  retention_in_days = 14
}
resource "aws_cloudwatch_log_group" "api" {
  name              = "/issue-classifier/dev/api"
  retention_in_days = 14
}
resource "aws_iam_role" "runtime" {
  name                 = "issue-classifier-dev-runtime"
  permissions_boundary = var.permissions_boundary_arn
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole"
    }]
  })
}
resource "aws_iam_role_policy" "runtime" {
  role = aws_iam_role.runtime.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.sut.arn}:*"
      },
      {
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel"]
        Resource = var.model_resource_arns
      }
    ]
  })
}
resource "aws_lambda_function" "sut" {
  function_name                  = "issue-classifier-dev"
  filename                       = var.lambda_zip
  source_code_hash               = filebase64sha256(var.lambda_zip)
  role                           = aws_iam_role.runtime.arn
  runtime                        = "python3.12"
  handler                        = "event_classifier.handler.lambda_handler"
  architectures                  = ["x86_64"]
  timeout                        = 25
  memory_size                    = 256
  reserved_concurrent_executions = 2
  environment {
    variables = { BEDROCK_MODEL_ID = var.model_id }
  }
  depends_on = [aws_cloudwatch_log_group.sut, aws_iam_role_policy.runtime]
}
resource "aws_apigatewayv2_api" "sut" {
  name          = "issue-classifier-dev"
  protocol_type = "HTTP"
}
resource "aws_apigatewayv2_integration" "sut" {
  api_id                 = aws_apigatewayv2_api.sut.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.sut.invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 30000
}
resource "aws_apigatewayv2_route" "sut" {
  for_each           = toset(["POST /v1/classifications", "GET /health"])
  api_id             = aws_apigatewayv2_api.sut.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.sut.id}"
  authorization_type = "AWS_IAM"
}
resource "aws_apigatewayv2_stage" "dev" {
  api_id      = aws_apigatewayv2_api.sut.id
  name        = "$default"
  auto_deploy = true
  default_route_settings {
    throttling_burst_limit = 5
    throttling_rate_limit  = 2
  }
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api.arn
    format = jsonencode({
      requestId = "$context.requestId", status = "$context.status",
      routeKey  = "$context.routeKey", responseLatency = "$context.responseLatency"
    })
  }
}
resource "aws_lambda_permission" "api" {
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.sut.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.sut.execution_arn}/*/*"
}
resource "aws_s3_bucket" "artifacts" {
  bucket        = var.artifact_bucket_name
  force_destroy = false
}
resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    id     = "expire-evaluation-reports"
    status = "Enabled"
    filter { prefix = "evaluation/" }
    expiration { days = 30 }
    noncurrent_version_expiration { noncurrent_days = 30 }
  }
}
resource "aws_s3_bucket_policy" "tls" {
  bucket = aws_s3_bucket.artifacts.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Deny", Principal = "*", Action = "s3:*"
      Resource  = [aws_s3_bucket.artifacts.arn, "${aws_s3_bucket.artifacts.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}
resource "aws_cloudwatch_metric_alarm" "errors" {
  alarm_name          = "issue-classifier-dev-errors"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.sut.function_name }
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  # TODO: add approved alarm_actions and prove notification delivery before production.
}

output "api_url" { value = aws_apigatewayv2_api.sut.api_endpoint }
output "artifact_bucket" { value = aws_s3_bucket.artifacts.id }
output "api_invoke_arn" { value = "${aws_apigatewayv2_api.sut.execution_arn}/*/*" }
output "lambda_name" { value = aws_lambda_function.sut.function_name }
output "log_group" { value = aws_cloudwatch_log_group.sut.name }
