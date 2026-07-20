# Only the AWS resources the application actually uses: two S3 buckets (raw
# uploads + HLS/DASH segments), the SQS transcode queue (+ DLQ), and a DynamoDB
# table for the movie catalog. These are provisioned into floci by
# `terraform apply`; the services then use them instead of self-creating them.
#
# There is no VPC/networking module: floci emulates the S3/SQS control plane on
# a single endpoint, so there is nothing to place inside a VPC. Network design
# (where a firewall/VPC/subnets would sit for a real AWS deploy) is documented
# in docs/infra-floci.md rather than provisioned here.

module "storage" {
  source       = "./modules/storage"
  project_name = var.project_name
}

module "queue" {
  source       = "./modules/queue"
  project_name = var.project_name
}

module "catalog" {
  source       = "./modules/catalog"
  project_name = var.project_name
}
