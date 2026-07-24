# Wiring values the services consume. After `terraform apply`, copy these into
# your .env (S3_VIDEO_BUCKET, S3_SEGMENTS_BUCKET, SQS_TRANSCODE_QUEUE_URL).

output "raw_bucket_name" {
  description = "S3 bucket for raw uploads (S3_VIDEO_BUCKET)."
  value       = module.storage.raw_bucket_name
}

output "segments_bucket_name" {
  description = "S3 bucket for HLS/DASH segments (S3_SEGMENTS_BUCKET)."
  value       = module.storage.segments_bucket_name
}

output "transcode_queue_url" {
  description = "SQS transcode queue URL (SQS_TRANSCODE_QUEUE_URL)."
  value       = module.queue.transcode_queue_url
}

output "dlq_url" {
  description = "SQS dead-letter queue URL (SQS_DLQ_URL)."
  value       = module.queue.dlq_url
}

output "catalog_table_name" {
  description = "DynamoDB catalog table (DYNAMODB_TABLE)."
  value       = module.catalog.table_name
}
