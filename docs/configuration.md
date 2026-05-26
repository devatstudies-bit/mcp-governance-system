# Configuration Reference

All MTGS configuration is driven by environment variables. In development, set these in a `.env` file at the project root. In production, inject them via Kubernetes secrets or Azure Key Vault.

---

## Application

| Variable | Required | Default | Description |
|---|---|---|---|
| `APP_ENV` | Yes | `development` | Environment: `development`, `staging`, `production`, `test` |
| `APP_SECRET_KEY` | Yes | — | Random secret ≥ 16 chars. **Change in production.** |
| `APP_DEBUG` | No | `false` | Enable debug mode. Must be `false` in production. |
| `APP_LOG_LEVEL` | No | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `APP_NAME` | No | `MTGS` | Application name (appears in logs and API responses) |
| `APP_VERSION` | No | `1.0.0` | Application version |

---

## Database

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | Yes | — | Async PostgreSQL DSN: `postgresql+asyncpg://user:pass@host:port/db` |
| `DATABASE_POOL_SIZE` | No | `10` | SQLAlchemy connection pool size |
| `DATABASE_MAX_OVERFLOW` | No | `20` | Max connections beyond pool_size |
| `DATABASE_POOL_TIMEOUT` | No | `30` | Seconds to wait for a connection |
| `DATABASE_ECHO` | No | `false` | Log all SQL queries. Use only in dev. |

---

## Redis

| Variable | Required | Default | Description |
|---|---|---|---|
| `REDIS_URL` | No | `redis://localhost:6379/0` | Redis connection URL for embedding cache |
| `CELERY_BROKER_URL` | No | `redis://localhost:6379/1` | Celery task broker |
| `CELERY_RESULT_BACKEND` | No | `redis://localhost:6379/2` | Celery result store |

For Azure Cache for Redis (TLS), use `rediss://` (note double `s`).

---

## Azure OpenAI

| Variable | Required | Default | Description |
|---|---|---|---|
| `AZURE_OPENAI_API_KEY` | Yes | — | Azure OpenAI resource API key |
| `AZURE_OPENAI_ENDPOINT` | Yes | — | Azure OpenAI resource endpoint (e.g., `https://your-resource.openai.azure.com`) |
| `AZURE_OPENAI_API_VERSION` | No | `2024-08-01-preview` | API version |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | No | `text-embedding-3-large` | Embedding model deployment name |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` | No | `gpt-4o` | Chat model deployment (used for fallback) |
| `AZURE_OPENAI_EMBEDDING_DIMENSIONS` | No | `3072` | Embedding vector dimensions (must match model) |

---

## Azure AI Search

| Variable | Required | Default | Description |
|---|---|---|---|
| `AZURE_SEARCH_ENDPOINT` | Yes | — | Azure AI Search service endpoint |
| `AZURE_SEARCH_API_KEY` | Yes | — | Admin API key for the search service |
| `AZURE_SEARCH_INDEX_NAME` | No | `mtgs-tool-embeddings` | Name of the vector index |
| `AZURE_SEARCH_VECTOR_FIELD` | No | `embedding` | Name of the vector field in the index |
| `AZURE_SEARCH_TOP_K` | No | `20` | Number of ANN neighbors to retrieve |

---

## Azure Key Vault (Optional)

Used in production to fetch secrets at runtime instead of injecting them as env vars.

| Variable | Required | Default | Description |
|---|---|---|---|
| `AZURE_KEY_VAULT_URL` | No | — | Key Vault URL (e.g., `https://your-kv.vault.azure.net`) |
| `AZURE_CLIENT_ID` | No | — | Service principal client ID |
| `AZURE_CLIENT_SECRET` | No | — | Service principal client secret |
| `AZURE_TENANT_ID` | No | — | Azure AD tenant ID |

If `AZURE_KEY_VAULT_URL` is set, secrets are loaded from Key Vault on startup. Managed Identity is preferred over service principal for AKS deployments.

---

## JWT Authentication

| Variable | Required | Default | Description |
|---|---|---|---|
| `JWT_SECRET_KEY` | Yes | — | JWT signing secret ≥ 32 chars. **Change in production.** |
| `JWT_ALGORITHM` | No | `HS256` | JWT signing algorithm |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | No | `60` | Access token lifetime in minutes |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | No | `7` | Refresh token lifetime in days |

---

## Notifications

| Variable | Required | Default | Description |
|---|---|---|---|
| `SLACK_WEBHOOK_URL` | No | — | Slack Incoming Webhook URL for conflict alerts |
| `SMTP_HOST` | No | — | SMTP server hostname |
| `SMTP_PORT` | No | `587` | SMTP server port |
| `SMTP_USER` | No | — | SMTP username |
| `SMTP_PASSWORD` | No | — | SMTP password |
| `SMTP_FROM` | No | `mtgs@yourdomain.com` | From address for email notifications |

MTGS also supports PagerDuty; configure the integration key per-environment via the API:
```bash
curl -X PATCH /v1/environments/{id} \
  -d '{"notification_config": {"pagerduty_integration_key": "..."}}'
```

---

## Governance Defaults

These are the system-wide defaults. Per-environment overrides are stored in `environments.policy` JSONB column.

| Variable | Required | Default | Description |
|---|---|---|---|
| `DEFAULT_SEMANTIC_SIMILARITY_THRESHOLD` | No | `0.80` | Cosine similarity above which Stage 3 flags a conflict |
| `DEFAULT_ROUTING_AMBIGUITY_THRESHOLD` | No | `0.30` | Routing split fraction above which Stage 4 flags `INTENT_AMBIGUITY` |
| `DEFAULT_PROBE_QUERY_COUNT` | No | `50` | Default number of probe queries per analysis run |
| `DEFAULT_SIMULATION_TRIALS` | No | `3` | LLM routing trials per probe query (majority vote) |
| `CI_FAIL_ON_SEVERITY` | No | `HIGH` | Minimum severity that causes CI gate to fail: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` |
| `SIMULATION_LLM_TEMPERATURE` | No | `0.0` | LLM temperature for routing simulation (0.0 = deterministic) |
| `EMBEDDING_CACHE_TTL_SECONDS` | No | `86400` | Redis TTL for embedding cache entries (default: 24 hours) |

---

## Rate Limiting

| Variable | Required | Default | Description |
|---|---|---|---|
| `RATE_LIMIT_PER_MINUTE` | No | `60` | API requests per minute per API key (standard endpoints) |
| `CI_WEBHOOK_RATE_LIMIT_PER_MINUTE` | No | `100` | Requests per minute for `/webhooks/ci-check` |

---

## Observability

| Variable | Required | Default | Description |
|---|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No | — | OpenTelemetry collector OTLP endpoint (e.g., `http://collector:4318`) |
| `OTEL_SERVICE_NAME` | No | `mtgs-api` | Service name in traces and metrics |

If `OTEL_EXPORTER_OTLP_ENDPOINT` is not set, OpenTelemetry is disabled and logs go to stdout only.

---

## Validation Rules

The following validation is applied at startup:

- **Production guards:** If `APP_ENV=production`, then `APP_DEBUG` must be `false`, and both `APP_SECRET_KEY` and `JWT_SECRET_KEY` must not contain `"change-me"`.
- **Azure endpoints:** Trailing slashes are stripped from `AZURE_OPENAI_ENDPOINT` and `AZURE_SEARCH_ENDPOINT`.
- **Float bounds:** `DEFAULT_SEMANTIC_SIMILARITY_THRESHOLD` and `DEFAULT_ROUTING_AMBIGUITY_THRESHOLD` must be in [0.0, 1.0].
- **Probe count:** `DEFAULT_PROBE_QUERY_COUNT` must be between 1 and 500.
- **Simulation trials:** `DEFAULT_SIMULATION_TRIALS` must be between 1 and 10.

If any validation fails, the application refuses to start and prints the specific error.
