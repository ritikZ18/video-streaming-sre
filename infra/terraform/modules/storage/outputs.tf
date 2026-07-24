output "raw_bucket_name" {
  value = aws_s3_bucket.raw_uploads.bucket
}

output "segments_bucket_name" {
  value = aws_s3_bucket.segments.bucket
}

