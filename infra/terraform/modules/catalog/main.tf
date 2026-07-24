resource "aws_dynamodb_table" "catalog" {
  name         = "${var.project_name}-catalog"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }

  tags = {
    Name = "${var.project_name}-catalog"
  }
}
