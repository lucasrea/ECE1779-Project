# Deploy to DigitalOcean Kubernetes

These steps deploy the project to a DigitalOcean Kubernetes (DOKS) cluster using the manifests in `k8s/`.

## Prerequisites

- A running DOKS cluster
- `kubectl` configured for that cluster
- `doctl` authenticated with DigitalOcean
- A `.env` file in the repo root containing `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, and `API_KEY_PEPPER`
- A `POSTGRES_PASSWORD` provided either as the optional second argument to `scripts/deploy_doks.sh` or via the `POSTGRES_PASSWORD` environment variable
- A gateway image pushed to DigitalOcean Container Registry that matches `k8s/gateway.yaml`

## 1. Connect to the cluster

```bash
doctl kubernetes cluster kubeconfig save <cluster-id-or-name>
kubectl config current-context
kubectl get nodes
```

## 2. Integrate the cluster with DOCR

```bash
doctl kubernetes cluster registry add <cluster-id-or-name>
```

## 3. Deploy the stack

Use the helper script to create the namespace, secrets, configmap, and apply the manifests:

```bash
scripts/deploy_doks.sh <grafana_admin_password> [postgres_password]
```

Example:

```bash
scripts/deploy_doks.sh password password
```

## 4. Verify the deployment

```bash
kubectl get pods -n golden-gate
kubectl get svc -n golden-gate
kubectl get pvc -n golden-gate
kubectl get hpa -n golden-gate
```

Expected checks:
- all pods are `Running`
- the Postgres PVC is `Bound`
- the `gateway` service gets an external IP

## 5. Test the public gateway

```bash
curl http://<EXTERNAL-IP>/health
```

```bash
curl -X POST http://<EXTERNAL-IP>/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Provider: openai" \
  -H "X-Model: gpt-4.1" \
  -d '{"messages":[{"role":"user","content":"Say hello in one sentence."}]}'
```

## 6. Access monitoring

```bash
kubectl port-forward -n golden-gate svc/prometheus 9090:9090
kubectl port-forward -n golden-gate svc/grafana 3000:3000
```

Then open:
- `http://localhost:9090`
- `http://localhost:3000`

Grafana login:
- username: `admin`
- password: the value you passed to `deploy_doks.sh`
