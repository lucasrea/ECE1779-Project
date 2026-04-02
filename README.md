# Golden Gate Gateway

A unified, high-availability LLM gateway that exposes a single OpenAI-compatible API surface for multiple providers (OpenAI, Anthropic, Google Gemini). Switch providers by changing a header — no code changes required.

## Quickstart

### Prerequisites

- Python 3.10
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- API keys for at least one provider

### Setup

1. Application:

```bash
uv venv --python 3.10
source .venv/bin/activate
uv pip install -r requirements.txt
```

2. Observability (Prometheus + Grafana):

Requires [Docker](https://docs.docker.com/get-docker/). From the project root:

```bash
docker compose up -d
```

| Service    | URL                   | Credentials(username/password)   |
|------------|-----------------------|---------------|
| Grafana    | http://localhost:3000 | admin/admin |
| Prometheus | http://localhost:9090 | —             |

The **Golden Gate Gateway - Metrics** dashboard is provisioned automatically — no manual import needed. Open Grafana and it will be available under **Dashboards**.

To verify Prometheus is scraping the app, visit `http://localhost:9090/targets` — the `golden-gate-gateway` job should show **State: UP**.

### Configure

Create a `.env` file in the project root with your provider API keys:

```
OPENAI_API_KEY="sk-..."
ANTHROPIC_API_KEY="sk-ant-..."
GEMINI_API_KEY="..."
API_KEY_PEPPER="set-a-long-random-string"
```

The server loads `.env` automatically on startup via `python-dotenv`.

### Run

```bash
source .venv/bin/activate
uvicorn src.api:app --reload
```

The server starts at `http://localhost:8000`.

## Kubernetes Deployment

This repo includes a DigitalOcean Kubernetes deployment path in `k8s/`.

Prerequisites:

- Access to the shared DigitalOcean team and DOKS cluster
- `doctl` installed
- `kubectl` installed

Authenticate and connect to the cluster:

```bash
doctl auth init
doctl kubernetes cluster kubeconfig save <cluster-name>
kubectl get nodes
```

Before applying the manifests:

1. Build and push the gateway image to the shared DigitalOcean Container Registry.
2. Update the image tag in `k8s/gateway.yaml` so it points to the exact image you pushed.
3. Replace the placeholder values in `k8s/config.yaml` locally, especially the provider API keys, `API_KEY_PEPPER`, and `GRAFANA_ADMIN_PASSWORD`.
4. Do not commit real secrets.
5. Make sure your DOKS cluster is authorized to pull from the `golden-gate` registry.

Apply the manifests in this order:

```bash
kubectl apply -f k8s/config.yaml
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/gateway.yaml
kubectl apply -f k8s/monitoring.yaml
```

Useful checks:

```bash
kubectl get pods -n golden-gate
kubectl get svc -n golden-gate
kubectl port-forward -n golden-gate svc/prometheus 9090:9090
kubectl port-forward -n golden-gate svc/grafana 3000:3000
```

In Kubernetes, Prometheus scrapes the gateway at `gateway:80/metrics`, and Grafana loads the provisioned dashboard automatically.

## API Reference

### `POST /v1/chat/completions`

**Headers**

| Header       | Required | Description                                      |
|--------------|----------|--------------------------------------------------|
| `Authorization` | Yes   | Bearer API key issued by gateway operators       |
| `X-Provider` | Yes      | Provider to route to: `openai`, `anthropic`, `gemini` |
| `X-Model`    | Yes      | Model name passed to the provider SDK            |

**Request body** (OpenAI-compatible)

```json
{
  "messages": [
    {"role": "system", "content": "You are a helpful assistant"},
    {"role": "user", "content": "Explain quantum computing"}
  ],
  "temperature": 0.7,
  "max_tokens": 1024
}
```

**Response**

```json
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "Quantum computing uses..."
      }
    }
  ],
  "usage": {
    "prompt_tokens": 15,
    "completion_tokens": 42
  }
}
```

### Sample requests

**OpenAI**

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer gg_live_<prefix>_<secret>" \
  -H "X-Provider: openai" \
  -H "X-Model: gpt-4.1" \
  -d '{"messages": [{"role": "user", "content": "Hello"}]}'
```

**Anthropic**

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer gg_live_<prefix>_<secret>" \
  -H "X-Provider: anthropic" \
  -H "X-Model: claude-haiku-4-5" \
  -d '{"messages": [{"role": "user", "content": "Hello"}]}'
```

**Google Gemini**

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer gg_live_<prefix>_<secret>" \
  -H "X-Provider: gemini" \
  -H "X-Model: gemini-2.5-flash" \
  -d '{"messages": [{"role": "user", "content": "Hello"}]}'
```

## API Key Management

Gateway client auth is managed with persistent bearer keys stored as hashes in Postgres (`api_keys` table).

Use the admin script:

```bash
python scripts/manage_api_keys.py create --owner "team-a"
python scripts/manage_api_keys.py list
python scripts/manage_api_keys.py revoke --prefix <key-prefix>
```

The `create` command prints the plaintext key once in the format `gg_live_<prefix>_<secret>`.

`API_KEY_PEPPER` is mixed into key hashing. Keep it private and consistent between key creation and request validation. If you change it, previously created keys will no longer validate.

### Local key management

With docker-compose Postgres:

```bash
DATABASE_URL=postgresql://postgres:password@localhost:5432/gateway \
python scripts/manage_api_keys.py create --owner "local-tester"
```

### End-to-end local auth test

1. Start services and rebuild to ensure env changes are loaded:

```bash
docker compose up -d --build
```

2. Confirm `.env` includes your provider key(s) and `API_KEY_PEPPER`.

3. Create a gateway API key:

```bash
source .venv/bin/activate
DATABASE_URL=postgresql://postgres:password@localhost:5432/gateway \
python scripts/manage_api_keys.py create --owner "local-tester"
```

4. Call the gateway with the printed bearer key:

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer gg_live_<prefix>_<secret>" \
  -H "X-Provider: anthropic" \
  -H "X-Model: claude-haiku-4-5" \
  -d '{"messages": [{"role": "user", "content": "Hello"}]}'
```

5. Negative checks:
   - remove `Authorization` header -> expect `401`
   - use an invalid key -> expect `401`

6. Revoke and verify:

```bash
python scripts/manage_api_keys.py revoke --prefix <key-prefix>
```

Retry the same request with that key and confirm it returns `401`.

### Kubernetes production key management

Option 1 (from your machine) via port-forward:

```bash
kubectl -n golden-gate port-forward svc/postgres 15432:5432
DATABASE_URL=postgresql://postgres:<POSTGRES_PASSWORD>@localhost:15432/gateway \
python scripts/manage_api_keys.py create --owner "evaluator-1"
```

Option 2 (inside cluster): run the same script in a one-off pod/job with the same `gateway-secrets`/`gateway-config` env injection pattern as the gateway deployment.

### Docker credential helper troubleshooting

If `docker compose up -d --build` fails with:

`error getting credentials ... "docker-credential-desktop": executable file not found in $PATH`

your Docker client is configured with a credential helper that is not available in the current shell. Fix by either:

- starting Docker Desktop and retrying, or
- adjusting `~/.docker/config.json` to use an installed helper (for example `osxkeychain`), or
- removing the `credsStore` entry temporarily.

### Fallback behaviour

If the primary provider fails, the gateway automatically tries the remaining providers in order: OpenAI, Anthropic, Gemini (skipping the one that already failed). If all providers fail, a `500` is returned.

## Architecture

```
Client
  │
  │  POST /v1/chat/completions
  │  Headers: X-Provider, X-Model
  │  Body: { messages, temperature, max_tokens }
  │
  ▼
┌──────────────────────────────────┐
│  FastAPI Gateway (src/api.py)    │
│                                  │
│  1. Resolve provider class from  │
│     PROVIDER_REGISTRY            │
│  2. Semantic cache lookup        │
│  3. to_provider_format()         │
│  4. provider.call()              │
│  5. normalize() → OpenAI shape   │
│  6. Cache store                  │
└──────────────────────────────────┘
         │           │           │
         ▼           ▼           ▼
      OpenAI    Anthropic     Gemini
```

### Key files

| File | Purpose |
|------|---------|
| `src/api.py` | FastAPI app, routing, fallback chain |
| `src/models.py` | Pydantic schemas, provider classes (transform + call + normalize) |
| `src/registry.py` | Self-registering provider registry via `@register_provider` decorator |
| `src/semantic_cache.py` | pgvector-backed semantic cache |

## Tests

### Unit tests

```bash
source .venv/bin/activate
make test
# or
python -m pytest -q
```

Tests mock all provider SDK calls so no API keys are needed to run them.

### Metrics / Grafana

Use the traffic simulator to emit fake metrics and verify all Grafana panels without real API keys:

```bash
python simulate_traffic.py              # 2 req/s, default mix
python simulate_traffic.py --rate 10   # faster
python simulate_traffic.py --fail-rate 0.4 --hit-rate 0.2  # stress error panels
```
Make sure `docker compose up -d` is running first so Prometheus scrapes the simulator's `/metrics` endpoint. By default, `prometheus_data/prometheus.yml` is configured to scrape `host.docker.internal:8000`, so either run the simulator on port 8000 or update the Prometheus scrape config to match any custom `--port` you choose.

## Video Demo
**https://youtu.be/wSiC2EXkwCo**
