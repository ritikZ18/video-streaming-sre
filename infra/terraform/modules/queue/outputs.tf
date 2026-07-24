output "transcode_queue_url" {
  value = aws_sqs_queue.transcode.url
}

output "transcode_queue_arn" {
  value = aws_sqs_queue.transcode.arn
}

output "dlq_url" {
  value = aws_sqs_queue.dlq.url
}
