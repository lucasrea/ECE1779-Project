# AI Interaction Report — Golden Gate Gateway

These are 3 examples of how we interacted with LLMs (GPT, Claude) to boost our productivity and learn in a meaningful way.

---

## Bootstrapping pgvector for Semantic Caching

### Prompt

We want to add a semantic cache to our FastAPI LLM gateway. The idea is: before calling a provider, embed the user's messages with sentence-transformers, then do a cosine similarity search in PostgreSQL using pgvector. If a close-enough result exists, return it directly. We're using asyncpg for async DB access. How should we structure the cache class and initialize the connection pool?

### AI Response

The AI suggested a `SemanticCache` class with an async `create()` classmethod that:
1. Created an asyncpg connection pool with `init=register_vector` (from `pgvector.asyncpg`) to register vector type codecs for every connection in the pool.
2. Created the `semantic_cache` table with an `embedding vector(384)` column and an HNSW index (`vector_cosine_ops`).
3. Exposed `lookup()` and `store()` methods using `<=>` (cosine distance) in a parameterized query.

Skeleton suggested:

```python
pool = await asyncpg.create_pool(url, init=register_vector)
model = SentenceTransformer("all-MiniLM-L6-v2")
```

### What the Team Did With It

- **What was useful:** The overall class structure, the `init=register_vector` pattern, and the HNSW index creation query were correct and saved significant time. The cosine similarity query using `1 - (embedding <=> $1) >= $2` was directly usable.

- **What was incorrect / not applicable:** The AI skipped a critical ordering issue: `register_vector` registers the `vector` type codec on each new connection, but the `vector` PostgreSQL *extension* must already exist in the database before the pool is created — otherwise `register_vector` fails with a codec error on first use. The AI's snippet went straight to `create_pool` without ensuring the extension existed first.

- **How we verified and fixed it:** Running the suggested code against a fresh `pgvector/pgvector:pg17` container (as in our `docker-compose.yml`) produced an asyncpg codec registration error. We diagnosed this by reading the `pgvector.asyncpg` source, then added a one-off bootstrap connection before the pool:

  ```python
  # Bootstrap: ensure the extension exists before pool creation
  bootstrap = await asyncpg.connect(url)
  await bootstrap.execute("CREATE EXTENSION IF NOT EXISTS vector")
  await bootstrap.close()

  pool = await asyncpg.create_pool(url, min_size=2, max_size=10, init=register_vector)
  ```

  We also kept a redundant `CREATE EXTENSION IF NOT EXISTS vector` inside `init_db()` as a safety measure for connections acquired from the pool. The final code is in [src/semantic_cache.py](src/semantic_cache.py).

---

## Metrics Recording Through the Fallback Chain

### Prompt

Our gateway has a fallback chain: if the requested provider fails, it tries OpenAI → Anthropic → Gemini in order. We're recording Prometheus metrics (request count, duration, transform time) keyed by provider and model. The problem is that when a fallback kicks in, our metrics still show the *original* provider instead of the one that actually served the request. How should we restructure the metric recording so it always reflects the provider that succeeded?

### AI Response

The AI recommended wrapping the fallback chain in a dataclass that carries the successful provider name, model, and transform time back to the caller:

```python
@dataclass
class FallbackResponse:
    provider: str
    model: str
    transform_time: float
    response: dict
```

It also recommended moving all `record_*` calls to *after* `_fallback_chain` resolves, so the `actual_provider` and `actual_model` variables could be overwritten from `FallbackResponse` before being passed to metrics:

```python
actual_provider = fallback_response.provider
actual_model    = fallback_response.model
transform_elapsed = fallback_response.transform_time
response        = fallback_response.response

record_transform(actual_provider, actual_model, transform_elapsed)
record_provider_call(actual_provider, actual_model, "success", call_elapsed)
```

### What the Team Did With It

- **What was useful:** The `FallbackResponse` dataclass pattern cleanly solved the "which provider actually ran?" problem without global state. Moving metric recording after fallback resolution was the right structural approach.

- **What was incorrect / not applicable:** The AI's sketch only recorded the *successful* call's metrics. It omitted recording the *failure* metrics for the original provider (and intermediate fallback failures), which meant our Grafana provider health panel showed no failures — making the fallback transparent in a misleading way.

- **How we verified and fixed it:** We checked the Grafana "Provider Health" dashboard after injecting an intentional failure: the counter for the broken provider showed zero failures. We added explicit `record_provider_call(..., "failure", elapsed)` calls both for the primary provider (before entering `_fallback_chain`) and inside the fallback loop for each provider that also fails:

  ```python
  # Primary provider failure — record before entering fallback
  record_provider_call(actual_provider, actual_model, "failure", first_call_elapsed)

  # Inside _fallback_chain loop, for each failed fallback attempt:
  record_provider_call(name, DEFAULT_MODELS[name], "failure", current_try_elapsed)
  ```

---

## Grafana Dashboard Panels for Custom LLM Metrics

### Prompt

We're using prometheus-fastapi-instrumentator to expose Prometheus metrics from our FastAPI app. We've also defined custom Counters and Histograms (llm_requests_total, llm_request_duration_seconds, cache_hits_total, etc.) labelled by provider and model. How do we write PromQL queries for a Grafana dashboard that shows: (1) request rate by provider, (2) p95 latency by provider, (3) cache hit ratio, and (4) estimated USD saved?

### AI Response

The AI provided four PromQL queries:

```promql
# (1) Request rate by provider
rate(llm_requests_total[5m])

# (2) p95 latency by provider
histogram_quantile(0.95, rate(llm_request_duration_seconds_bucket[5m]))

# (3) Cache hit ratio
rate(cache_hits_total[5m]) / (rate(cache_hits_total[5m]) + rate(cache_misses_total[5m]))

# (4) USD saved
increase(cache_cost_saved_usd_total[1h])
```

It also noted that `prometheus-fastapi-instrumentator` auto-instruments HTTP-level metrics (status code, method, handler) and these would appear alongside the custom metrics.

### What the Team Did With It

- **What was useful:** The PromQL structure for queries (1), (2), and (4) was correct and used directly. The `histogram_quantile` syntax and the `increase()` vs `rate()` distinction for cost savings were accurate.

- **What was incorrect / not applicable:** Two issues arose in practice:
  1. The AI's query (1) omitted the `by (provider, model)` aggregation clause, so Grafana collapsed all providers into a single series. Similarly, query (2) needed `by (le, provider)` inside `rate()` before passing to `histogram_quantile`.
  2. `prometheus-fastapi-instrumentator`'s auto-generated metrics use label names like `handler` and `method`, not `provider` — so we had to make sure Grafana panels targeting provider health used *only* our custom `llm_requests_total` metric, not the instrumentator's `http_requests_total`. The AI had not distinguished between these two metric families.

- **How we verified and fixed it:** We opened Prometheus at `localhost:9090` and ran each query manually to inspect the returned label sets. We discovered the missing aggregation by noticing all lines on the rate panel had the same value. The corrected queries used in our provisioned dashboard (`grafana/grafana_dashboard_setup.json`) are:

  ```promql
  # (1) corrected
  rate(llm_requests_total[5m]) by (provider, model)

  # (2) corrected
  histogram_quantile(0.95, sum(rate(llm_request_duration_seconds_bucket[5m])) by (le, provider))
  ```

  We also identified that the Grafana dashboard JSON needed `"datasource": "Prometheus"` set explicitly on each panel, as the AI-generated skeleton used a placeholder variable that broke auto-provisioning. After these fixes, the dashboard loaded correctly on `docker compose up` without manual edits.
