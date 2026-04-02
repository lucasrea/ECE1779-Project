# Final Project Report: Golden Gate Gateway

## 1. Team Information

- Member 1: Yingxuan Hu, 1006881377
- Member 2: Jignwen Xu, 1011282675
- Member 3: King Wang, 1008235081
- Member 4: Lucas Rea, 1003099531

## 2. Motivation

Modern AI applications often depend on one cloud provider's API, creating risk from outages, rate limits, or pricing changes. 
Golden Gate Gateway addresses this by providing a single OpenAI-compatible endpoint that routes requests transparently to OpenAI, Anthropic, or Google Gemini, with provider-switching via header and automatic fallback.

This project is significant because it demonstrates resilience, portability, and monitored observability for production-grade model serving.

## 3. Objectives

1. Build a provider-agnostic LLM gateway with normalized OpenAI-style interface.
2. Support OpenAI, Anthropic, and Google Gemini via common endpoint.
3. Implement provider failover: primary provider → remaining providers.
4. Add semantic caching (pgvector) to reduce repeated inference costs.
5. Provide observability with Prometheus + Grafana and confirm metrics reliability.
6. Deploy using Kubernetes (DOKS manifests provided) for real cluster operation.

## 4. Technical Stack

- Python 3.10
- FastAPI (HTTP gateway)
- Pydantic (schemas/validation)
- PostgreSQL (+ pgvector extension) for semantic cache
- `uvicorn` as ASGI server
- Docker Compose for local observability stack
- Kubernetes (DigitalOcean Kubernetes Service) for production orchestration
- Prometheus + Grafana for metrics
- Pytest for automated tests
- `simulate_traffic.py` for load & metric simulation

Deployment approach: Kubernetes (manifests under `k8s/`, including `gateway.yaml`, `postgres.yaml`, `monitoring.yaml`).

## 5. Features

- Single REST entrypoint: `POST /v1/chat/completions`
- Provider selection: `X-Provider` header (`openai`, `anthropic`, `gemini`)
- Model selection: `X-Model` header
- Provider template translation: request/response mapping per vendor
- Fallback chain: if chosen provider fails, try other providers automatically
- Semantic cache lookup/store with pgvector cosine similarity
- Observability metrics: request counts, latencies, provider errors, cache hits/misses, fallback events
- DB-backed cache for repeated prompt efficiency
- Test coverage with provider call mocking


## 6. User Guide

### 6.1 Local Setup

Prerequisites:
- Python 3.10
- Docker (for monitoring stack)
- `doctl` + `kubectl` (for Kubernetes deployment)

Steps:

1. Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Set environment variables in `.env`:

```env
OPENAI_API_KEY="sk-..."
ANTHROPIC_API_KEY="sk-ant-..."
GEMINI_API_KEY="..."
DATABASE_URL="postgresql://user:pass@localhost:5432/pgvector"
```

3. Start observability:

```bash
docker compose up -d
```

4. Run app:

```bash
uvicorn src.api:app --reload
```

5. Verify app:

- `http://localhost:8000/docs` (Swagger UI)
- `http://localhost:9090/targets` (Prometheus)
- `http://localhost:3000` (Grafana, admin/admin)

### 6.2 API usage

#### POST /v1/chat/completions

Headers:
- `Content-Type: application/json`
- `X-Provider: openai|anthropic|gemini`
- `X-Model: model-name`

Body (OpenAI format):

```json
{
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Tell me a haiku."}
  ],
  "temperature": 0.7,
  "max_tokens": 100
}
```

Example:

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Provider: openai" \
  -H "X-Model: gpt-4.1" \
  -d '{"messages":[{"role":"user","content":"Hello"}]}'
```

Fallback behavior:
- If provider returns non-2xx / error, gateway retries next provider order: openai → anthropic → gemini.
- Final error returns HTTP 500 with diagnostics.

### 6.3 Semantic cache

- Cache key generated from request text embedding.
- Cache hit returns stored provider response quickly (avoids external API call).
- Configure `PGVECTOR_THRESHOLD` etc in env.

### 6.4 Screenshots

- `docs/screenshots/api-request.png`
- `docs/screenshots/grafana-dashboard.png`

## 7. Development Guide

### 7.1 Repo and workflow

```bash
git clone https://github.com/lucasrea/ECE1779-Project.git
cd ECE1779-Project
```

### 7.2 Database and local storage

- PostgreSQL with `pgvector` extension required for semantic cache.
- `k8s/postgres.yaml` provision uses `PersistentVolumeClaim` for data.
- Local test mode can use an in-memory sqlite fallback if `DATABASE_URL` points to sqlite.

Create DB and extension:

```sql
CREATE DATABASE gateway;
\c gateway;
CREATE EXTENSION IF NOT EXISTS vector;
```

### 7.3 Tests

- Unit tests:
  - `pytest -q` (mocks provider SDK)
- Integration tests:
  - `pytest tests/integration` (if available)
- Linting:
  - `ruff check .`

### 7.4 Observability tests

1. Start services (`docker compose up -d`)
2. Run traffic simulator:

```bash
python simulate_traffic.py --rate 5 --duration 120
```

3. Validate in Grafana dashboard and ensure causally visible metrics.

## 8. Deployment Information

### 8.1 Live URL
#### TO BE REPLACED
- Application URL: `https://golden-gate-gateway.example.com` 
- Grafana URL: `https://grafana.example.com`

### 8.2 Kubernetes instructions

```bash
doctl auth init
doctl kubernetes cluster kubeconfig save <cluster-name>
kubectl config current-context
kubectl apply -f k8s/config.yaml
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/gateway.yaml
kubectl apply -f k8s/monitoring.yaml
```

Monitor:

- `kubectl get pods -n golden-gate`
- `kubectl get svc -n golden-gate`

## 9. Video Demo

- Video URL: `https://youtu.be/wSiC2EXkwCo`

## 10. AI Assistance & Verification (Summary)

- AI contributions:
  - Architecture exploration (API design, fallback flow, semantic cache)
  - Containerization and Kubernetes manifest creation guidance
  - Code scaffolding and debugging suggestions for provider adapters
  - README and documentation wording

- Representative AI limitation:
  - AI initially generated an incorrect Kubernetes Service type (ClusterIP instead of LoadBalancer), captured in `ai_session.md`.
  - Another issue: Mistakenly suggested sending plain API keys in repository files; we corrected by using env variables and secrets.

- Verification approach:
  - Automated tests (`pytest`) validate request/response and fallback logic with mocks.
  - Manual cURL and Postman calls confirmed provider routing and normalization.
  - Prometheus metrics checks (`/targets`, query metrics) and Grafana dashboards confirm observability.
  - `simulate_traffic.py` load tests validate behaviors and error-handling.

> See `ai_session.md` for detailed AI dialogue excerpts and explicit issue tracing.

## 10. Individual Contributions

- Member 1: API gateway core logic (`src/api.py`), provider registry (`src/registry.py`), fallback engine.
- Member 2: Semantic cache implementation (`src/semantic_cache.py`), PostgreSQL pgvector integration, local setup docs.
- Member 3: Kubernetes manifests (`k8s/*`), orchestration, testing scripts.
- Member 4: observability (`prometheus_data/*`, Grafana dashboard)

Align contributions to commit history using `git log --author=<name>`.

## 11. Lessons Learned and Concluding Remarks

- Learned how to unify heterogeneous LLM providers under one API, increase fault tolerance, and apply semantics-based caching.
- Gained practical experience with Kubernetes deployment lifecycle and observability pipelines.
- Reinforced discipline in verifying AI-generated recommendations through tests and code reviews.
- The project demonstrates a real-world architecture for cloud-native LLM services and provides a robust foundation for future extensions (API keys rotation, RBAC,  usage quotas, multi-region failover).

---