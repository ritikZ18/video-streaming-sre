variable "aws_region" {
  type        = string
  description = "AWS region for all resources."
  default     = "us-west-2"
}

variable "project_name" {
  type        = string
  description = "Base name used for tagging and resource names."
  default     = "streamsre"
}

