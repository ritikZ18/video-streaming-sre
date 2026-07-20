# AWS provider pointed at the floci local emulator (LocalStack-compatible).
#
# floci speaks the real AWS wire protocol on http://localhost:4566, so the only
# changes vs. a real-AWS provider are: dummy static creds, path-style S3, the
# skip_* validators (there is no real IAM/metadata endpoint to call), and the
# endpoints{} override. To target real AWS instead, drop access_key/secret_key,
# the skip_* flags and the endpoints{} block, and use normal AWS credentials.
provider "aws" {
  region     = var.aws_region
  access_key = "test"
  secret_key = "test"

  s3_use_path_style           = true
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    s3  = var.aws_endpoint_url
    sqs = var.aws_endpoint_url
  }
}
