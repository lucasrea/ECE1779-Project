"""
Self-contained Prometheus + Grafana test.

Starts a FastAPI app that exposes /metrics, then drives all metric helper
functions in a background loop.

Run:
    python simulate_traffic.py              # default: 2 req/s
    python simulate_traffic.py --rate 10   # faster
    python simulate_traffic.py --port 9000 # different port
"""

import argparse
import asyncio
import logging
import random
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from src.observability.metrics import (
    model_for,
    record_cache_hit,
    record_cache_miss,
    record_transform,
    record_provider_call,
    start_price_refresh_loop,
    stop_price_refresh_loop,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PROVIDERS = ["OpenAI", "Gemini", "Claude"]

_FAKE_RESPONSES = {
    "OpenAI": "This is a fake GPT-4.1 response with several words to estimate token count.",
    "Claude": "This is a fake Claude Haiku response with several words to estimate token count.",
    "Gemini": "This is a fake Gemini Flash response with several words to estimate token count.",
}

# ── CLI args parsed at module level so uvicorn can import the module cleanly ──

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--rate",     type=float, default=2.0)
parser.add_argument("--hit-rate", type=float, default=0.3)
parser.add_argument("--fail-rate",type=float, default=0.1)
parser.add_argument("--port",     type=int,   default=8000)
parser.add_argument("--help", "-h", action="store_true")
_args, _ = parser.parse_known_args()


async def _traffic_loop(rate: float, hit_rate: float, fail_rate: float) -> None:
    miss_rate = 1.0 - hit_rate - fail_rate
    interval  = 1.0 / rate
    sent = 0

    logger.info(
        "Traffic loop started  rate=%.1f/s  miss=%.0f%%  hit=%.0f%%  fail=%.0f%%",
        rate, miss_rate * 100, hit_rate * 100, fail_rate * 100,
    )

    while True:
        t_start = time.perf_counter()
        provider = random.choice(PROVIDERS)
        model    = model_for(provider)
        roll     = random.random()

        if roll < miss_rate:
            # cache miss → transform → provider call
            record_cache_miss(provider, model)

            t0 = time.perf_counter()
            await asyncio.sleep(random.uniform(0.001, 0.01))
            record_transform(provider, model, time.perf_counter() - t0)

            t1 = time.perf_counter()
            await asyncio.sleep(random.uniform(0.1, 1.5))

            if roll < miss_rate - fail_rate or miss_rate <= fail_rate:
                record_provider_call(provider, model, "success", time.perf_counter() - t1)
            else:
                record_provider_call(provider, model, "failure", time.perf_counter() - t1)

        elif roll < miss_rate + hit_rate:
            # cache hit — no provider call, just cost savings
            record_cache_hit(provider, model, _FAKE_RESPONSES[provider])

        else:
            # explicit failure path
            record_cache_miss(provider, model)

            t0 = time.perf_counter()
            await asyncio.sleep(random.uniform(0.001, 0.01))
            record_transform(provider, model, time.perf_counter() - t0)

            t1 = time.perf_counter()
            await asyncio.sleep(random.uniform(0.05, 0.3))
            record_provider_call(provider, model, "failure", time.perf_counter() - t1)

        sent += 1
        if sent % 20 == 0:
            logger.info("Metrics emitted: %d events so far", sent)

        elapsed   = time.perf_counter() - t_start
        remaining = max(0.0, interval - elapsed)
        await asyncio.sleep(remaining)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await start_price_refresh_loop()
    task = asyncio.create_task(
        _traffic_loop(_args.rate, _args.hit_rate, _args.fail_rate)
    )
    yield
    task.cancel()
    await stop_price_refresh_loop()


app = FastAPI(lifespan=lifespan)
Instrumentator().instrument(app).expose(app)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    if _args.help:
        print(__doc__)
        print("Options:")
        print("  --rate FLOAT       Simulated requests/s  (default: 2.0)")
        print("  --hit-rate FLOAT   Fraction that are cache hits  (default: 0.3)")
        print("  --fail-rate FLOAT  Fraction that are failures    (default: 0.1)")
        print("  --port INT         Port to listen on             (default: 8000)")
        raise SystemExit(0)

    uvicorn.run(
        "simulate_traffic:app",
        host="0.0.0.0",
        port=_args.port,
        reload=False,
    )
