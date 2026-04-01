FROM python:3.10-slim AS builder

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip

# CPU-only PyTorch keeps the image ~1.5 GB smaller than the full CUDA build
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Keep the model cache location stable. The embedding model is downloaded at
# runtime so cross-platform builds do not fail on transient Hugging Face access.
ENV SENTENCE_TRANSFORMERS_HOME=/app/models

# ---- runtime ----
FROM python:3.10-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
ENV SENTENCE_TRANSFORMERS_HOME=/app/models

COPY src/ ./src/

EXPOSE 8000

CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
