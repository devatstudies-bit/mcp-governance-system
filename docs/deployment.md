# Deployment

This guide covers deploying MTGS to production on Azure. The stack runs on Azure Kubernetes Service (AKS) with managed PostgreSQL, Redis, OpenAI, and AI Search services.

---

## Azure Resource Topology

```
Azure Subscription
├── Resource Group: rg-mtgs-prod
│   ├── AKS Cluster (mtgs-aks)
│   │   ├── Namespace: mtgs
│   │   │   ├── Deployment: api (3 replicas)
│   │   │   ├── Deployment: worker-analysis (2 replicas)
│   │   │   ├── Deployment: worker-simulation (1 replica)
│   │   │   └── Ingress (nginx)
│   │   └── Namespace: monitoring
│   │       ├── Grafana
│   │       └── OpenTelemetry Collector
│   │
│   ├── Azure Database for PostgreSQL Flexible Server
│   │   └── mtgs_prod database
│   │
│   ├── Azure Cache for Redis (Premium, with persistence)
│   │
│   ├── Azure OpenAI Service
│   │   ├── Deployment: text-embedding-3-large
│   │   └── Deployment: gpt-4o (for simulation)
│   │
│   ├── Azure AI Search (Standard S1 or higher)
│   │   └── Index: mtgs-tool-embeddings
│   │
│   ├── Azure Key Vault (secrets management)
│   │
│   └── Azure Blob Storage (analysis artifacts, reports)
```

---

## Pre-Deployment Checklist

- [ ] Azure resource group created
- [ ] PostgreSQL Flexible Server provisioned (min: 2 vCPU, 8GB RAM)
- [ ] Azure Cache for Redis provisioned (min: C1 Standard)
- [ ] Azure OpenAI deployed with `text-embedding-3-large` model
- [ ] Azure AI Search service provisioned (Standard S1)
- [ ] Azure Key Vault created and secrets populated
- [ ] AKS cluster created (min: 3 nodes, Standard_D4s_v3)
- [ ] Container registry (ACR) created and linked to AKS
- [ ] Domain and TLS certificate configured

---

## 1. Build and Push Container Image

```bash
# Build
docker build -f docker/Dockerfile -t mtgs:1.0.0 .

# Tag and push to ACR
ACR_NAME=myacr
docker tag mtgs:1.0.0 $ACR_NAME.azurecr.io/mtgs:1.0.0
az acr login --name $ACR_NAME
docker push $ACR_NAME.azurecr.io/mtgs:1.0.0
```

---

## 2. Kubernetes Secrets

Store all secrets in Azure Key Vault and sync to Kubernetes via the Azure Key Vault Secret Provider:

```yaml
# k8s/secret-provider.yaml
apiVersion: secrets-store.csi.x-k8s.io/v1
kind: SecretProviderClass
metadata:
  name: mtgs-secrets
  namespace: mtgs
spec:
  provider: azure
  parameters:
    usePodIdentity: "false"
    useVMManagedIdentity: "true"
    keyvaultName: "mtgs-keyvault-prod"
    objects: |
      array:
        - |
          objectName: app-secret-key
          objectType: secret
        - |
          objectName: jwt-secret-key
          objectType: secret
        - |
          objectName: azure-openai-api-key
          objectType: secret
        - |
          objectName: azure-search-api-key
          objectType: secret
        - |
          objectName: database-url
          objectType: secret
    tenantId: "your-tenant-id"
  secretObjects:
    - secretName: mtgs-secrets
      type: Opaque
      data:
        - objectName: app-secret-key
          key: APP_SECRET_KEY
        - objectName: jwt-secret-key
          key: JWT_SECRET_KEY
        - objectName: azure-openai-api-key
          key: AZURE_OPENAI_API_KEY
        - objectName: azure-search-api-key
          key: AZURE_SEARCH_API_KEY
        - objectName: database-url
          key: DATABASE_URL
```

---

## 3. API Deployment

```yaml
# k8s/api-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mtgs-api
  namespace: mtgs
spec:
  replicas: 3
  selector:
    matchLabels:
      app: mtgs-api
  template:
    metadata:
      labels:
        app: mtgs-api
    spec:
      containers:
        - name: api
          image: myacr.azurecr.io/mtgs:1.0.0
          command: ["uvicorn", "mtgs.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
          ports:
            - containerPort: 8000
          env:
            - name: APP_ENV
              value: "production"
            - name: APP_LOG_LEVEL
              value: "INFO"
            - name: AZURE_OPENAI_ENDPOINT
              value: "https://your-resource.openai.azure.com"
            - name: AZURE_SEARCH_ENDPOINT
              value: "https://your-search.search.windows.net"
            - name: AZURE_OPENAI_EMBEDDING_DEPLOYMENT
              value: "text-embedding-3-large"
            - name: REDIS_URL
              value: "redis://mtgs-redis:6379/0"
            - name: CELERY_BROKER_URL
              value: "redis://mtgs-redis:6379/1"
            - name: CELERY_RESULT_BACKEND
              value: "redis://mtgs-redis:6379/2"
          envFrom:
            - secretRef:
                name: mtgs-secrets
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "2000m"
              memory: "2Gi"
          readinessProbe:
            httpGet:
              path: /readiness
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 30
            periodSeconds: 30
          volumeMounts:
            - name: secrets-store
              mountPath: "/mnt/secrets"
              readOnly: true
      volumes:
        - name: secrets-store
          csi:
            driver: secrets-store.csi.k8s.io
            readOnly: true
            volumeAttributes:
              secretProviderClass: "mtgs-secrets"
```

---

## 4. Worker Deployments

```yaml
# k8s/worker-analysis-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mtgs-worker-analysis
  namespace: mtgs
spec:
  replicas: 2
  selector:
    matchLabels:
      app: mtgs-worker-analysis
  template:
    metadata:
      labels:
        app: mtgs-worker-analysis
    spec:
      containers:
        - name: worker
          image: myacr.azurecr.io/mtgs:1.0.0
          command:
            - "celery"
            - "-A"
            - "mtgs.workers.celery_app"
            - "worker"
            - "--loglevel=info"
            - "-Q"
            - "analysis,embeddings"
            - "--concurrency=4"
          # same env + secrets as API
          resources:
            requests:
              cpu: "1000m"
              memory: "1Gi"
            limits:
              cpu: "4000m"
              memory: "4Gi"
---
# worker-simulation: same shape, queue=simulation, concurrency=2, replicas=1
```

---

## 5. Database Setup

```bash
# Run migrations against production DB
DATABASE_URL="postgresql+asyncpg://user:pass@prod-host:5432/mtgs_prod" \
  alembic upgrade head
```

For zero-downtime deploys, always use Alembic's `--sql` flag to review migrations before running:

```bash
alembic upgrade head --sql   # prints SQL, does not execute
```

---

## 6. Azure AI Search Index

The vector index must be created before the first embedding is stored. MTGS creates the index automatically on first startup if it doesn't exist, but you can also create it manually:

```bash
# Via MTGS CLI
mtgs admin create-search-index --env prod

# Or via Azure CLI
az search index create \
  --service-name your-search \
  --name mtgs-tool-embeddings \
  --fields-config @k8s/search-index-schema.json
```

The index requires a `Collection(Edm.Single)` field named `embedding` with `dimensions=3072` and `vectorSearchProfile` configured for cosine similarity.

---

## 7. Ingress + TLS

```yaml
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: mtgs-ingress
  namespace: mtgs
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/proxy-body-size: "10m"
    nginx.ingress.kubernetes.io/rate-limit: "60"
spec:
  tls:
    - hosts:
        - api.mtgs.yourdomain.com
      secretName: mtgs-api-tls
  rules:
    - host: api.mtgs.yourdomain.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: mtgs-api
                port:
                  number: 8000
```

---

## 8. Environment Variables Reference (Production)

All production-critical variables that **must** be set:

```bash
# Application
APP_ENV=production
APP_SECRET_KEY=<random-32-char-secret>   # From Key Vault
APP_DEBUG=false
APP_LOG_LEVEL=INFO

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/mtgs_prod

# Redis
REDIS_URL=rediss://mtgs-redis.redis.cache.windows.net:6380/0   # TLS for Azure Cache
CELERY_BROKER_URL=rediss://mtgs-redis.redis.cache.windows.net:6380/1
CELERY_RESULT_BACKEND=rediss://mtgs-redis.redis.cache.windows.net:6380/2

# Azure OpenAI
AZURE_OPENAI_API_KEY=<from-key-vault>
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com

# Azure AI Search
AZURE_SEARCH_ENDPOINT=https://your-search.search.windows.net
AZURE_SEARCH_API_KEY=<from-key-vault>

# Auth
JWT_SECRET_KEY=<random-64-char-secret>   # From Key Vault

# Notifications (optional but recommended for prod)
SLACK_WEBHOOK_URL=https://hooks.slack.com/...
SMTP_HOST=smtp.sendgrid.net
SMTP_USER=apikey
SMTP_PASSWORD=<sendgrid-api-key>
SMTP_FROM=mtgs-alerts@yourdomain.com

# Observability
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
OTEL_SERVICE_NAME=mtgs-api

# Governance
CI_FAIL_ON_SEVERITY=HIGH
DEFAULT_SEMANTIC_SIMILARITY_THRESHOLD=0.80
```

---

## 9. Horizontal Pod Autoscaler

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: mtgs-api-hpa
  namespace: mtgs
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: mtgs-api
  minReplicas: 3
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

---

## 10. Monitoring

**Key dashboards to set up in Grafana:**

| Dashboard | Key Metrics |
|---|---|
| API Health | Request rate, p99 latency, error rate per endpoint |
| Conflict Detection | Analysis run duration by stage, conflict detection rate |
| Worker Queue | Celery queue depth, task processing time, failure rate |
| LLM Usage | Azure OpenAI token usage, Anthropic API calls, costs |
| Business | New tools/day, conflicts/day, health score trend |

**Alerts to configure:**

| Alert | Condition |
|---|---|
| API down | `/readiness` returns non-200 for 2+ minutes |
| Queue backlog | `analysis` or `simulation` queue depth > 50 for 5+ minutes |
| High error rate | API 5xx rate > 1% over 5 minutes |
| Analysis failure spike | > 5 failed analysis runs in 10 minutes |
| CRITICAL conflict detected | Severity=CRITICAL in any environment |

---

## Upgrade Procedure

1. Build and push new image tag
2. Update image tag in Kubernetes manifests
3. Run `alembic upgrade head` (or use init-container pattern)
4. `kubectl apply -f k8s/` — Kubernetes performs rolling update
5. Monitor `/readiness` health checks during rollout
6. Rollback: `kubectl rollout undo deployment/mtgs-api`
