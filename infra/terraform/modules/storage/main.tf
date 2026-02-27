resource "aws_s3_bucket" "raw_uploads" {
  bucket = "${var.project_name}-raw-uploads"

  tags = {
    Name = "${var.project_name}-raw-uploads"
  }
}

resource "aws_s3_bucket" "segments" {
  bucket = "${var.project_name}-hls-segments"

  tags = {
    Name = "${var.project_name}-hls-segments"
  }
}

