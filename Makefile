.PHONY: help up down build logs logs-% test lint typecheck scan scan-secrets tf-plan tf-apply clean demo

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

# --- Local Dev ---
up: ## Start all services with Docker Compose
	docker compose up -d --build
	@echo "Frontend:        http://localhost:3001"
	@echo "Upload API:      http://localhost:8000/docs"
	@echo "Beacon API:      http://localhost:8001/docs"
	@echo "Origin (HLS):    http://localhost:8080"
	@echo "Prometheus:      http://localhost:9090"
	@echo "Grafana:         http://localhost:3000"
	@echo "Alertmanager:    http://localhost:9093"

down: ## Stop all services
	docker compose down

build: ## Build all images without starting containers
	docker compose build

logs: ## Tail logs for all services
	docker compose logs -f

logs-%: ## Tail logs for a specific service, e.g. make logs-upload-api
	docker compose logs -f $*

# --- Quality: Backend ---
test: ## Run backend tests (Python services)
	@echo "Running tests for upload-api..."
	cd services/upload-api && pytest -q
	@echo "Running tests for transcode-worker..."
	cd services/transcode-worker && pytest -q
	@echo "Running tests for beacon-collector..."
	cd services/beacon-collector && pytest -q

lint: ## Lint Python code with ruff
	ruff check services
	ruff format --check services

typecheck: ## Type-check Python services with mypy
	mypy services/upload-api/app services/transcode-worker/app services/beacon-collector/app

# --- Security ---
scan: ## Run Trivy scan on all service images
	bash security/scan-images.sh

scan-secrets: ## Run gitleaks to detect secrets
	bash security/scan-secrets.sh

# --- Terraform (optional, when infra is wired) ---
tf-plan: ## Terraform plan for staging
	cd infra/terraform && terraform plan -var-file=environments/staging.tfvars

tf-apply: ## Terraform apply for staging
	cd infra/terraform && terraform apply -var-file=environments/staging.tfvars

# --- Housekeeping ---
clean: ## Remove containers, images, volumes, and Python caches
	docker compose down -v --rmi local || true
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +

demo: up ## Start stack and seed a demo video
	@sleep 10
	@bash scripts/seed-test-video.sh
	@echo "Demo ready. Open http://localhost:3001"

