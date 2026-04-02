#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ "${1:-}" == "" ]]; then
  echo "Usage: scripts/deploy_doks.sh <grafana_admin_password> [postgres_password]"
  exit 1
fi

if [[ ! -f .env ]]; then
  echo ".env not found in repo root"
  exit 1
fi

source .env

if [[ -z "${OPENAI_API_KEY:-}" || -z "${ANTHROPIC_API_KEY:-}" || -z "${GEMINI_API_KEY:-}" ]]; then
  echo "Missing provider keys in .env"
  exit 1
fi

if [[ -z "${API_KEY_PEPPER:-}" ]]; then
  echo "Missing API_KEY_PEPPER in .env"
  exit 1
fi

GRAFANA_ADMIN_PASSWORD="$1"
POSTGRES_PASSWORD="${2:-${POSTGRES_PASSWORD:-}}"

if [[ -z "${POSTGRES_PASSWORD}" ]]; then
  echo "Missing POSTGRES_PASSWORD: provide it as the second argument or set POSTGRES_PASSWORD in .env"
  exit 1
fi
kubectl create namespace golden-gate --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic gateway-secrets -n golden-gate \
  --from-literal=OPENAI_API_KEY="${OPENAI_API_KEY}" \
  --from-literal=ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}" \
  --from-literal=GEMINI_API_KEY="${GEMINI_API_KEY}" \
  --from-literal=API_KEY_PEPPER="${API_KEY_PEPPER}" \
  --from-literal=POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" \
  --from-literal=GRAFANA_ADMIN_PASSWORD="${GRAFANA_ADMIN_PASSWORD}" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl create configmap gateway-config -n golden-gate \
  --from-literal=CACHE_SIMILARITY_THRESHOLD=0.95 \
  --from-literal=EMBEDDING_MODEL=all-MiniLM-L6-v2 \
  --from-literal=POSTGRES_HOST=postgres \
  --from-literal=POSTGRES_PORT=5432 \
  --from-literal=POSTGRES_USER=postgres \
  --from-literal=POSTGRES_DB=gateway \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/gateway.yaml
kubectl apply -f k8s/monitoring.yaml

kubectl rollout status statefulset/postgres -n golden-gate --timeout=300s
kubectl rollout status deploy/gateway -n golden-gate --timeout=300s
kubectl rollout status deploy/prometheus -n golden-gate --timeout=300s
kubectl rollout status deploy/grafana -n golden-gate --timeout=300s

kubectl get pods -n golden-gate
kubectl get svc -n golden-gate
kubectl get pvc -n golden-gate
kubectl get hpa -n golden-gate
