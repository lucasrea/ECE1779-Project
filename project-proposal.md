# Golden Gate Gateway

**Yingxuan Hu &nbsp;|&nbsp; Jingwen Xu &nbsp;|&nbsp; King Wang &nbsp;|&nbsp; Lucas Rea**

---

For a service interacting with Large Language models (LLMs), there can be significant technical challenges integrating with different providers. Developers have to design endpoints to interact with each provider's unique API and schema – leading to redundancy in operations. In addition to redundancy in the codebase, if clients were to submit semantically similar queries between different providers' models (or even to the same provider and model) this may cause a significant increase in costs and response speed due to the continuous recomputation. Thus, we decided to design Golden Gate Gateway, a high-availability gateway to standardize LLM interactions. Developers can replace a string of LLM names to switch between models without the worries of query redundancy or the need of code changing; We also designed unified monitoring jogs for developers or financial teams to provide overall observability across platforms that would potentially utilize this AI gateway.

---

## Existing Solutions & Limitations

| Solution | Strengths | Limitations |
|---|---|---|
| **LLM Gateway (theopenco)** | Unified API, many providers, cost tracking | No cross-provider caching, limited observability, self-hosting complexity |
| **AssemblyAI LLM Gateway** | Clean API, multi-turn, tool calling | No semantic caching, limited provider coverage, not self-hosted |
| **Apiary Gateway** | Open-source, semantic caching, observability | Early-stage caching, limited SLAs, incomplete feature normalization |
| **Commercial LLM Gateways** | Unified API, enterprise-friendly | Opaque internals, vendor lock-in, weak financial observability |

### Gaps We Can Fill In

1. **True cross-provider semantic caching**
   No existing solution guarantees that a query answered by OpenAI will be reused when switching to Anthropic if the user repeats the same request.

2. **Fully standardized API surface**
   Providers differ in:
   - Chat completion / tool calling formats
   - Streaming behavior
   - Token counting
   - Safety settings
   - System prompt handling

   No gateway fully normalizes these.

3. **Enterprise-grade observability for finance teams**
   Most gateways track cost per request, but none provide:
   - Cross-provider cost reconciliation
   - Per-team or per-project cost attribution
   - Anomaly detection for runaway usage

4. **High-availability routing with deterministic fallbacks**
   Some gateways offer fallbacks, but not:
   - Deterministic routing rules
   - SLA-aware provider selection
   - Multi-region failover

---

## Objective and Key Features

Our objective is to build a cloud-native LLM abstraction layer with semantic memory and observability. It provides a unified OpenAI-Compatible chat completions API that abstracts the differences between various LLM providers; a semantic cache to intercept and answer repeat queries, optimizing cost and speed; and a persistent monitoring log. The entire system is orchestrated via Kubernetes to ensure scalability and reliability.

### Core Features

#### Unified API

This is an abstraction that layer exposes a single endpoint(e.g. /v1/chat/completions) that follows the OpenAI specification. It embeds a transformation engine that maps the incoming JSON request to a specific format which is required by the downstream provider. For example, it converts OpenAI messages into Anthropic prompt, changing one format to the other. In this case, users can switch from gpt-4o to claude-3-opus by simply changing a string in their request header, without changing their application code.

This endpoint also supports streaming and non-streaming responses across providers.

If OpenAI response is server error with 500 code, the gateway automatically retries the request with Anthropic.

Other necessary services like authentication are also provided for reliability.

#### Semantic Search

For every request, the gateway will convert it into a vector embedding, and maintain it in PostgreSQL with pgvector; A similarity search will be performed in the database by the unified endpoint, returning cached responses for 95% similarity matches which bypasses the LLM provider entirely. Persistent storage is intentionally designed and maintained to keep all the queries for a long-run.

#### Orchestration Approach

We choose DigitalOcean Kubernetes (DOKS) to orchestrate unified API and semantic search.

#### Database Schema

A schema is applied to logs of all requests across providers, logs are stored in PostgreSQL.

#### Persistence Storage

DigitalOcean Volumes (Block Storage) is used for semantic search.

#### Deployment Provider

DigitalOcean

#### Monitoring Setup

There are three metrics under monitoring:

- **Provider health:** the success/failure rates for OpenAI, Anthropic, etc.
- **Cost savings:** real-time calculation of money saved via the semantic caching.
- **Latency:** tracking time spent in format transformation and provider response.

Prometheus collects the metrics from the gateway, a Grafana dashboard will visualize the results.

#### Advanced Features

- **Auto-scaling:** more pods in DOKS will be triggered during high traffic.
- **Secret Management:** Kubernetes Secrets will be used for high security.

---

## Course Requirement Fulfillment

The followings are the details of project requirement fulfillment:

| Course Requirement | G3 Implementation Detail |
|---|---|
| **Containerization** | Multi-stage Docker builds for the FastAPI Gateway and Celery/Redis Worker (for background embedding). |
| **State Management** | PostgreSQL 16 with pgvector for both relational metadata and vector storage. |
| **Persistence** | DigitalOcean Volumes mounted to the Postgres StatefulSet to ensure the "Cache Memory" is permanent. |
| **Orchestration** | DigitalOcean Kubernetes (DOKS). Deployment for the API; StatefulSet for DB; ConfigMaps for provider settings. |
| **Monitoring** | Prometheus scraping metrics from the Gateway and Grafana for visualization. |
| **Advanced Feature 1** | Auto-scaling: K8s Horizontal Pod Autoscaler (HPA) triggers more Gateway pods during high-traffic LLM bursts. |
| **Advanced Feature 2** | Secrets Management: Using Kubernetes Secrets to securely store and inject API keys into the environment. |

---

This project focuses on Text-based LLMs; multi-modal (image, audio, video) generation is out of scope to ensure the 2-month timeline is met. Our deployment priority is the Kubernetes Manifests, Persistent Volumes, and Load Balancing logic. These constraints and scope clarification makes our project pragmatic within the project timeframe.

---

## Tentative Plan

We plan to use the first three weeks to finish system implementation, and leverage the last three weeks for testing, debugging and documentation. Here is a detailed breakdown:

| Week | Tasks | Owner |
|---|---|---|
| Mar. 2nd - Mar. 8th | Chat Completion Endpoint design · Build Semantic Memory | Jingwen Xu |
| Mar. 9th - Mar. 15th | Maintain Unified Monitoring Logs by Prometheus · Build Grafana UI | King |
| Mar. 16th - Mar. 22th | Containerization & Orchestration | |
| Mar. 23th - Mar. 29th | Testing & Debugging · Clean up source code · Final Report | |
| Mar. 30th - Apr. 4th | Final Report · AI Interaction Report · Record Video Demo · Recheck & Submit | |

---

## Initial Independent Reasoning


### Architecture Choices



For our architecture, we intentionally selected technologies that both satisfy the course requirements and reinforce concepts covered in lectures and assignments. First, for the cloud provider, we chose DigitalOcean. This decision aligns directly with the course requirement to deploy on DigitalOcean or Fly.io, and we selected DigitalOcean because our gateway is designed to be stateless, with all persistent data stored in PostgreSQL. Thus, it aligns well with Kubernetes' scaling model on DigitalOcean, as stateless services can be replicated without complex session management. This design simplifies horizontal scaling and improves fault tolerance, which reinforces cloud-native principles discussed in lectures.The tradeoff is that DigitalOcean provides fewer advanced managed services compared to other providers like AWS or GCP, meaning we must configure more infrastructure components ourselves. However, this is beneficial pedagogically as it allows us to learn fundamental concepts such as clusters, volumes, and networking.

For orchestration, we chose Kubernetes instead of Docker Swarm. Kubernetes was covered extensively in lectures, and using it allows us to implement Deployments, Services, StatefulSets, PersistentVolumes, and Horizontal Pod Autoscaling in a production-like environment. The tradeoff is increased complexity such as k8s configuration overhead, YAML management, and operational learning curves compared to Docker Swarm. However, this complexity can also be a great opportunity to learn cloud-native orchestration that aligns with industry standards.

For persistent storage, we selected PostgreSQL 16 with pgvector, deployed as a StatefulSet and backed by DigitalOcean Volumes. PostgreSQL satisfies the mandatory relational database requirement, while pgvector enables semantic caching as part of our application logic. The tradeoff is that managing a stateful database inside Kubernetes requires careful configuration of PersistentVolumes and backups, which adds operational complexity. However, this approach ensures that application state survives pod restarts and redeployments, which fulfills the project's state management requirement. In addition to the use of pgvector as a semantic cache, industry standards also operate with auditing in mind, thus a simple PostgreSQL database to store query transactions would be desired as well.

Overall, these architectural choices balance course alignment, practical learning value, and realistic cloud-native design within a manageable project scope.

### Anticipated Challenges


The most difficult part of our project will likely be integrating all the different components into a stable, working system. Each individual technology (FastAPI, PostgreSQL, Kubernetes, Prometheus, etc.) is manageable on its own, but combining them introduces many possible points of failure. Since our project includes both application logic and infrastructure configuration, small mistakes in one layer can easily affect the entire system.

On the application side, building a unified LLM gateway is more complex than it first appears. Different providers have different request formats, authentication methods, and error responses. Creating a clean abstraction layer that translates different formats without breaking functionality will require careful design and testing. The semantic caching feature using pgvector also adds difficulty. We need to generate embeddings, store them correctly, and define an appropriate similarity threshold. If the threshold is too low, we may return incorrect cached responses; if it is too high, the cache becomes ineffective.

On the infrastructure side, Kubernetes configuration is expected to be challenging. We need to correctly set up Deployments for the API, a StatefulSet for PostgreSQL, PersistentVolumes for data durability, and Services for networking. Any misconfiguration in environment variables, secrets, storage, or service routing could cause deployment failures. In addition, configuring Horizontal Pod Autoscaling and ensuring that Prometheus can scrape metrics from scaling pods adds another layer of complexity.

Monitoring and debugging a cloud application will also require extra attention. We must define clear metrics (e.g., latency, error rate, cache hit ratio) and structured logs so that issues can be diagnosed efficiently.

Overall, the biggest challenge is not one specific technology, but making sure all components work together reliably in a cloud-native environment.

### Early Development Approach


Our initial development strategy was to build the project incrementally, starting from a minimal working system and gradually layering in more advanced features. Instead of trying to implement all components at once, we decided to first focus on establishing a stable core: a simple FastAPI gateway connected to PostgreSQL, containerized with Docker Compose for local development. We believe that having a small but functional end-to-end pipeline early would reduce integration risk later and allow us to test assumptions before introducing additional complexity such as k8s orchestration, autoscaling, and observability.

Once the core request flow is working (API request → provider call → response stored in database), we planned to add the semantic caching layer using pgvector. This staged approach helps isolate potential issues; for example, if caching behaves incorrectly, we can debug it without questioning whether the infrastructure or provider integration is the cause. After the backend logic is stable, we intend to shift focus to deployment on DigitalOcean Kubernetes and then integrate monitoring and autoscaling features.

In terms of team responsibilities, we aimed to divide work by logical system boundaries rather than by tools alone. One team member would focus primarily on backend API design and provider abstraction, ensuring clean request handling and translation logic. Another member would take ownership of infrastructure and orchestration, including Kubernetes manifests, persistent volumes, secrets management, and autoscaling. The last two members would focus on the database schema, semantic caching implementation, and observability setup (Prometheus metrics and Grafana dashboards). This division allows each member to specialize while still requiring collaboration at integration points.

---

## AI Assistance Disclosure
