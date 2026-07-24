resource "aws_sqs_queue" "dlq" {
  name = "${var.project_name}-transcode-dlq"
}

resource "aws_sqs_queue" "transcode" {
  name                       = "${var.project_name}-transcode-queue"
  visibility_timeout_seconds = 600
  message_retention_seconds  = 345600

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })
}

