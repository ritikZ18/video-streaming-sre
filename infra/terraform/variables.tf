variable "aws_region" {
  type        = string
  description = "AWS region for all resources (floci accepts any; matches ./floci.sh env)."
  default     = "us-east-1"
}

variable "aws_endpoint_url" {
  type        = string
  description = "AWS endpoint override for the floci local emulator. Set to \"\" to target real AWS (also remove the endpoints/skip_* in provider.tf)."
  default     = "http://localhost:4566"
}

variable "project_name" {
  type        = string
  description = "Base name used for tagging and resource names."
  default     = "streamsre"
}
