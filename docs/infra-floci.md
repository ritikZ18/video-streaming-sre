# Infrastructure: Terraform + floci (local AWS)

This project targets AWS (S3 for storage, SQS for the transcode queue) but runs
**entirely locally, at zero cost**, against **floci** — a LocalStack-compatible
AWS emulator. The same Terraform and the same application code would run against
real AWS by changing only the endpoint/credentials.

---

## 0. Storage durability: persistent vs ephemeral (read this first)

floci is **in-memory** — every restart of floci (or the host/Docker) wipes it.
That is fine for a transient queue, but it also erased uploaded videos and their
catalog. So the **durable** state is deliberately kept **out of floci**, in
persistent local services with Docker volumes, and only the throwaway SQS queue
stays in floci:

| Data | Where it lives now | Persistence | Endpoint (in-container) |
|---|---|---|---|
| S3 objects (raw uploads + HLS segments) | **MinIO** (S3-compatible) | ✅ volume `minio_data` | `http://minio:9000` |
| Movie catalog (metadata + job status) | **dynamodb-local** | ✅ volume `dynamo_data` | `http://dynamodb-local:8000` |
| Transcode queue + DLQ | **floci** | ❌ in-memory (self-heals) | `http://host.docker.internal:4566` |

Both MinIO and dynamodb-local are ordinary services in this repo's
`docker-compose.yml`. Consequences:

- **Uploaded videos survive floci restarts.** Verified: upload a clip, `docker
  restart floci`, and the catalog row + segments + playback are all still there.
- **Credentials.** `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` double as the
  MinIO root user/password, so the secret must be **≥ 8 chars** (MinIO rejects
  shorter). We use `minioadmin` / `minioadmin`; floci and dynamodb-local ignore
  creds, so one pair works for all three.
- **Public-read segments.** MinIO enforces bucket policies (floci did not). The
  one-shot **`storage-bootstrap`** service (image `minio/mc`) creates both
  buckets and sets `streamsre-hls-segments` to anonymous **download**, so the
  origin's unsigned nginx proxy can serve `.m3u8`/`.m4s`. It's idempotent and
  reruns on every `up`. The DynamoDB table + SQS queue still self-heal in-app.
- **Browse your objects** at the MinIO console: `http://localhost:9001`
  (login `minioadmin` / `minioadmin`).
- **boto3 needs no code change** — with a custom endpoint + port it already uses
  path-style addressing, which MinIO serves natively.
- **Origin** proxies `/hls/…` to the `object_store` upstream (`minio:9000`), not
  floci. Stored manifest URLs (`http://localhost:8080/hls/<job>/master.m3u8`) are
  unchanged.

To point at **real AWS**, set `S3_ENDPOINT_URL` / `DYNAMODB_ENDPOINT_URL` to the
AWS endpoints (or empty) with real creds — MinIO and dynamodb-local drop out and
the same code hits S3 + DynamoDB.

---

## 1. What floci is

floci is a single container that listens on `http://localhost:4566` and speaks
the **real AWS wire protocol** (same request signing and JSON/XML/Query shapes
the AWS SDK and CLI already send). Because of that, no application code changes
are required — you point `*_ENDPOINT_URL` at `:4566` instead of `amazonaws.com`
and every `boto3` / `aws` call behaves as if it hit AWS.

floci lives in its **own** stack (not this repo's compose), typically at
`~/floci-stack`:

```bash
./floci.sh up       # start (listens on :4566)
./floci.sh env      # prints AWS_* export lines
./floci.sh status   # health
./floci.sh stop     # stop, keep data
```

Its env contract (mirrored in this repo's `.env.example`):

```
AWS_ENDPOINT_URL=http://localhost:4566
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
AWS_DEFAULT_REGION=us-east-1
```

> LocalStack note: floci is API-compatible with LocalStack (same `:4566`, same
> protocol). If you prefer LocalStack, run it on `:4566` with `SERVICES=s3,sqs`
> and everything below works unchanged.

---

## 2. Which AWS services / endpoints this project needs

Three AWS services, now split across durable local backends (see §0) — only SQS
still runs in floci:

| AWS service | Backend | Used for | Resources |
|---|---|---|---|
| **S3** | MinIO (`minio:9000`) | Raw uploads + generated HLS/DASH segments | `streamsre-raw-uploads`, `streamsre-hls-segments` |
| **DynamoDB** | dynamodb-local (`dynamodb-local:8000`) | Movie catalog + job status | `streamsre-catalog` |
| **SQS** | floci (`:4566`) | Decouples upload from transcoding | `streamsre-transcode-queue`, `streamsre-transcode-dlq` |

MinIO and dynamodb-local are compose services reached by name on the compose
network. **floci** (SQS) runs on the host, so containers reach it via
`http://host.docker.internal:4566` — `extra_hosts: "host.docker.internal:host-gateway"`
in `docker-compose.yml` makes that name resolve on both Docker Desktop and
native Docker Engine. From the host (Terraform, `aws` CLI) floci is
`http://localhost:4566`.

> The Terraform in `infra/terraform` still models all of this against a single
> floci endpoint (it predates the MinIO/dynamodb-local split and documents the
> real-AWS resource shapes). At runtime the app uses the split endpoints from
> `.env`; Terraform is not required to run the stack.

---

## 3. How Terraform is wired to floci

`infra/terraform/provider.tf` is a normal AWS provider with four local-emulation
tweaks:

```hcl
provider "aws" {
  region     = var.aws_region        # us-east-1
  access_key = "test"                # dummy static creds
  secret_key = "test"

  s3_use_path_style           = true # http://<host>/<bucket>/<key>, not vhost
  skip_credentials_validation = true # no real STS to validate against
  skip_metadata_api_check     = true # no EC2 metadata endpoint
  skip_requesting_account_id  = true

  endpoints {
    s3  = var.aws_endpoint_url        # http://localhost:4566
    sqs = var.aws_endpoint_url
  }
}
```

`infra/terraform/main.tf` provisions **only** what the app uses:

- `modules/storage` — the two S3 buckets
- `modules/queue` — the SQS transcode queue + DLQ (with a redrive policy)

There is intentionally **no VPC/networking module**: floci emulates the S3/SQS
*control plane* on one endpoint, so there is nothing to place inside a VPC.
(An earlier version provisioned a VPC + subnets that no service consumed and
that floci doesn't serve — it was removed. See §6 for where networking would
sit in a real deploy.)

To target **real AWS** instead of floci: remove `access_key`/`secret_key`, the
`skip_*` flags and the `endpoints{}` block, set `aws_endpoint_url = ""`, and use
normal AWS credentials. The resources are identical.

---

## 4. End-to-end local workflow

```bash
# 1. Start floci (separate stack)
make floci-up                # -> ~/floci-stack/floci.sh up

# 2. Provision buckets + queues into floci
make tf-apply                # terraform init + apply against :4566

# 3. Configure this repo's services
cp .env.example .env         # values already match floci + terraform

# 4. Start the app
make up                      # docker compose up --build

# 5. Seed a video and watch it flow through the pipeline
bash scripts/seed-test-video.sh
```

`make bootstrap` does steps 1–2, and `make demo` does 1–5.

Data flow:

```
upload-api  --PUT-->  s3://streamsre-raw-uploads/<job>/<file>
upload-api  --send--> sqs://streamsre-transcode-queue  {job_id, s3_key}
transcode-worker  --receive--> job
   ffmpeg (one pass) -> CMAF fMP4 segments + master.m3u8 (HLS) + manifest.mpd (DASH)
transcode-worker  --PUT-->  s3://streamsre-hls-segments/<job>/...
origin (nginx)  --proxy-->  s3://streamsre-hls-segments/  (cached, CDN-edge stand-in)
web player  <--GET--  http://localhost:8080/hls/<job>/master.m3u8  (or manifest.mpd)
```

---

## 5. Verifying floci resources with the AWS CLI

```bash
eval "$(~/floci-stack/floci.sh env)"   # or export AWS_* manually

aws --endpoint-url http://localhost:4566 s3 ls
aws --endpoint-url http://localhost:4566 sqs list-queues
aws --endpoint-url http://localhost:4566 \
    s3 ls s3://streamsre-hls-segments/ --recursive
```

---

## 6. Where a firewall / VPC would sit on real AWS (documented, not built)

floci has no network layer to secure, so this is design-only:

- **VPC + private subnets** for `transcode-worker` and any datastore; public
  subnets only for the origin/load balancer.
- **Edge firewall** (FortiGate / AWS WAF / security groups) in front of the load
  balancer: allow `443` inbound, restrict any admin surface to a VPN CIDR.
- **S3**: block public access; the origin (or CloudFront with an OAC) is the only
  reader of the segments bucket.
- **SQS**: least-privilege IAM so the upload-api may only `SendMessage` and the
  worker only `ReceiveMessage`/`DeleteMessage`.

These map 1:1 onto the Terraform above once you point it at real AWS.
