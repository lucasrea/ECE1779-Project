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
```

The server loads `.env` automatically on startup via `python-dotenv`.

### Run

```bash
source .venv/bin/activate
uvicorn src.api:app --reload
```

The server starts at `http://localhost:8000`.

## API Reference

### `POST /v1/chat/completions`

**Headers**

| Header       | Required | Description                                      |
|--------------|----------|--------------------------------------------------|
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
  -H "X-Provider: openai" \
  -H "X-Model: gpt-4.1" \
  -d '{"messages": [{"role": "user", "content": "Hello"}]}'
```

**Anthropic**

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Provider: anthropic" \
  -H "X-Model: claude-haiku-4-5" \
  -d '{"messages": [{"role": "user", "content": "Hello"}]}'
```

**Google Gemini**

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Provider: gemini" \
  -H "X-Model: gemini-2.5-flash" \
  -d '{"messages": [{"role": "user", "content": "Hello"}]}'
```

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
| `src/semantic_cache.py` | JSON-file cache (placeholder for pgvector) |

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

Make sure `docker compose up -d` is running first so Prometheus scrapes the simulator's `/metrics` endpoint.
