# Final Project Report: Golden Gate Gateway

## 1. Team Information

- Member 1: Yingxuan Hu, 1006881377, alvin.hu@mail.utoronto.ca
- Member 2: Jingwen Xu, 1011282675,
- Member 3: King Wang, 1008235081, jyang.wang@mail.utoronto.ca
- Member 4: Lucas Rea, 1003099531,

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
- Docker
- Docker Compose for local multi-container development
- Kubernetes (DigitalOcean Kubernetes Service) for production orchestration
- Prometheus + Grafana for application metrics
- DigitalOcean Insights and Resource Alerts for provider-side monitoring
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
- Provider-side monitoring via DigitalOcean Insights and Resource Alerts
- DB-backed cache for repeated prompt efficiency
- Test coverage with provider call mocking

These features satisfy the course requirements by combining Docker and Docker Compose for local multi-container development, PostgreSQL plus persistent storage for state management, Kubernetes Deployments/Services/PersistentVolumeClaims for orchestration on DigitalOcean, and monitoring through Prometheus, Grafana, DigitalOcean Insights, and Resource Alerts.

Advanced features implemented in the final system include high availability through multiple gateway replicas behind a DigitalOcean load balancer, security through API-key authentication and Kubernetes secrets, and automatic provider fallback for resilience.


## 6. User Guide

### 6.1 Local Setup

Prerequisites:
- Python 3.10
- Docker
- `doctl` + `kubectl` (for DigitalOcean Kubernetes deployment)

Steps:

1. Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

2. Set environment variables in `.env`:

```env
OPENAI_API_KEY="sk-..."
ANTHROPIC_API_KEY="sk-ant-..."
GEMINI_API_KEY="..."
API_KEY_PEPPER="set-a-long-random-string"
```

If you received the credential archive from the TA email handoff, place the provided `.env` file in the repository root instead of creating one manually.

3. Start the full local stack:

```bash
docker compose up -d
```

| Service    | URL                   | Credentials(username/password)   |
|------------|-----------------------|---------------|
| Grafana    | http://localhost:3000 | admin/admin |
| Prometheus | http://localhost:9090 | —             |

The **Golden Gate Gateway - Metrics** dashboard is provisioned automatically — no manual import needed. Open Grafana and it will be available under **Dashboards**.

To verify Prometheus is scraping the app, visit `http://localhost:9090/targets` — the `golden-gate-gateway` job should show **State: UP**.

4. Verify the app:

- `http://localhost:8000/health`
- `http://localhost:8000/docs`
- `http://localhost:9090/targets`
- `http://localhost:3000`

5. Create a local API key for authenticated requests:

```bash
python scripts/manage_api_keys.py create --owner "local-dev"
```

Copy the plaintext key that the script prints. It is shown only once.

### 6.2 API usage

#### POST /v1/chat/completions

Headers:
- `Content-Type: application/json`
- `Authorization: Bearer <your-api-key>`
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
  -H "Authorization: Bearer <your-api-key>" \
  -H "X-Provider: openai" \
  -H "X-Model: gpt-4.1" \
  -d '{"messages":[{"role":"user","content":"Hello"}]}'
```

Fallback behavior:
- If the selected provider fails, the gateway retries the remaining providers using the configured fallback order, skipping the provider that was originally selected.
- Final error returns HTTP 500 with diagnostics.

### 6.3 Semantic cache

- Cache key generated from request text embedding.
- Cache hit returns stored provider response quickly (avoids external API call).
- Configure `CACHE_SIMILARITY_THRESHOLD` in env or in the Kubernetes `gateway-config` ConfigMap.

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
- Local Docker Compose uses the named Docker volume `pgdata` for persistence.
- `k8s/postgres.yaml` uses a `PersistentVolumeClaim` for data in Kubernetes.
- The application bootstraps the `vector` extension and `semantic_cache` table automatically on startup.

### 7.3 Tests

- Unit tests:
  - `pytest -q` (mocks provider SDK)
- Linting:
  - `flake8 .`

### 7.4 Observability tests

1. Start services:

```bash
docker compose up -d
```

2. Generate sample traffic:

```bash
for i in $(seq 1 5)
do
  curl -s -X POST http://localhost:8000/v1/chat/completions \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer <your-api-key>" \
    -H "X-Provider: openai" \
    -H "X-Model: gpt-4.1" \
    -d '{"messages":[{"role":"user","content":"Hello"}]}' > /dev/null
done
```

3. Validate in Prometheus and Grafana.

Credentials sent to TA.

## 8. Deployment Information

### 8.1 Live URL
- API base URL: `http://159.203.54.95`
- Application URL (Swagger UI): `http://159.203.54.95/docs`
- Health check: `http://159.203.54.95/health`
- The bare root URL `http://159.203.54.95/` is expected to return `404 Not Found` because the application does not define a `/` route.
- For authenticated live API requests, use `Authorization: Bearer <your-api-key>` with the live API key included in the credential archive that was sent separately to the TA as required by the course instructions.
- Prometheus and Grafana are exposed internally in Kubernetes and can be accessed with `kubectl port-forward` after authenticating with the cluster credentials included in the credential archive.
- The credential archive also includes the deployed Grafana login information.

Live API example:

```bash
curl -X POST http://159.203.54.95/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-api-key>" \
  -H "X-Provider: openai" \
  -H "X-Model: gpt-4.1" \
  -d '{"messages":[{"role":"user","content":"Hello"}]}'
```

### 8.2 Kubernetes instructions

```bash
doctl auth init
doctl kubernetes cluster kubeconfig save golden-gate-doks
kubectl port-forward -n golden-gate svc/prometheus 9090:9090
kubectl port-forward -n golden-gate svc/grafana 3000:3000
```

If you need to redeploy from the provided credentials:

```bash
scripts/deploy_doks.sh <grafana_admin_password> <postgres_password>
```

Monitor:

- `kubectl get pods -n golden-gate`
- `kubectl get svc -n golden-gate`
- `kubectl get pvc -n golden-gate`

Detailed deployment notes are in `docs/digitalocean-deploy.md`.

## 9. Video Demo

- Video URL: `https://drive.google.com/file/d/1h491pllbcls26wxBYMARrWXvBXNOgumU/view?usp=drive_link`

## 10. AI Assistance & Verification (Summary)

- AI contributions:
  - Architecture exploration (API design, fallback flow, semantic cache)
  - Containerization and Kubernetes manifest creation guidance
  - Code scaffolding and debugging suggestions for provider adapters
  - README and documentation wording

- Representative AI limitation:
  - AI initially generated an incorrect Kubernetes Service type (ClusterIP instead of LoadBalancer), captured in `ai-session.md`.
  - Another issue: Mistakenly suggested sending plain API keys in repository files, and we corrected this by using env variables and secrets.

- Verification approach:
  - Automated tests (`pytest`) validate request/response and fallback logic with mocks.
  - Manual cURL and Postman calls confirmed provider routing and normalization.
  - Prometheus metrics checks (`/targets`, query metrics) and Grafana dashboards confirm observability.
  - `simulate_traffic.py` load tests validate behaviors and error-handling.

> See `ai-session.md` for detailed AI dialogue excerpts and explicit issue tracing.

## 11. Individual Contributions

- Member 1: API gateway core logic (`src/api.py`), provider registry (`src/registry.py`), fallback engine.
- Member 2: Semantic cache implementation (`src/semantic_cache.py`), PostgreSQL pgvector integration, local setup docs.
- Member 3: Kubernetes manifests (`k8s/*`), orchestration, testing scripts.
- Member 4: observability (`prometheus_data/*`, Grafana dashboard).

Align contributions to commit history using `git log --author=<name>`.

## 12. Lessons Learned and Concluding Remarks

- Learned how to unify heterogeneous LLM providers under one API, increase fault tolerance, and apply semantics-based caching.
- Gained practical experience with Kubernetes deployment lifecycle and observability pipelines.
- Reinforced discipline in verifying AI-generated recommendations through tests and code reviews.
- The project demonstrates a real-world architecture for cloud-native LLM services and provides a robust foundation for future extensions (API keys rotation, RBAC,  usage quotas, multi-region failover).
---