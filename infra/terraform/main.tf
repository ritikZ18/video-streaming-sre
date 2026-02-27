module "networking" {
  source       = "./modules/networking"
  project_name = var.project_name
  aws_region   = var.aws_region
}

module "storage" {
  source       = "./modules/storage"
  project_name = var.project_name
}

module "queue" {
  source       = "./modules/queue"
  project_name = var.project_name
}

