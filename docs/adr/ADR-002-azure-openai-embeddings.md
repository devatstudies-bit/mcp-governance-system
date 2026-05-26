# ADR-002: Azure OpenAI for Embeddings (text-embedding-3-large)

**Status:** Accepted  
**Date:** 2025-05  
**Deciders:** AI Platform Team

---

## Context

MTGS's Stage 3 semantic analysis depends on embedding tool descriptions into high-dimensional vectors and comparing them via cosine similarity. The embedding model is the single biggest lever on semantic conflict detection quality:

- A weak embedding model produces false positives (flagging unrelated tools) and false negatives (missing real semantic overlaps)
- The model must produce consistent embeddings across all tools in a registry — this rules out mixing models
- The enterprise deployment context requires data residency options and predictable pricing

---

## Decision Drivers

- **Quality:** Precision > 90% on semantic overlap detection (NFR-ACC-001)
- **Consistency:** All tools in a registry must use the same model version — can't mix models
- **Data residency:** Enterprise customers may require EU or US region processing
- **Existing infrastructure:** Most enterprise customers running Azure already have Azure OpenAI provisioned
- **Dimensions:** Higher dimensions = more expressive similarity space. `text-embedding-3-large` produces 3072-dimensional vectors

---

## Options Considered

| Model | Dimensions | Quality | Data Residency | Cost |
|---|---|---|---|---|
| **Azure OpenAI text-embedding-3-large** | 3072 | ✅ Highest | ✅ Azure regions | $$ |
| OpenAI text-embedding-3-large (direct) | 3072 | ✅ Highest | ⚠️ OpenAI regions only | $$ |
| OpenAI text-embedding-3-small | 1536 | ✅ Good | ⚠️ OpenAI regions only | $ |
| Cohere embed-v3 | 1024 | ✅ Good | ⚠️ Cohere regions | $$ |
| Sentence Transformers (self-hosted) | 768 | ⚠️ Good | ✅ Full control | $ (GPU) |

---

## Decision

**Azure OpenAI `text-embedding-3-large`** via the `openai` Python SDK (which supports Azure endpoints).

Key parameters:
- Dimensions: `3072` (maximum, for best discrimination)
- API version: `2024-08-01-preview`
- Deployment: customer-provisioned under their Azure subscription (no MTGS data leaves their tenant)

The embedding client is designed behind a protocol interface (`EmbeddingClient`) so the model can be swapped without changing the pipeline. Cohere and self-hosted modes are planned for Phase 4 (air-gapped deployments, see ADR-003).

---

## Consequences

**Positive:**
- Best-in-class semantic similarity quality at production scale
- Azure data residency — tool descriptions stay within the customer's Azure tenant
- Customers already provisioning Azure OpenAI for their AI agents can reuse the same resource
- Pluggable interface means model can be changed without touching pipeline logic

**Negative:**
- Dependency on Azure OpenAI availability (mitigated by retry logic with exponential backoff)
- Cost scales with registry size (number of tool definition changes that trigger re-embedding)
- Air-gapped enterprise customers cannot use this model (Phase 4 adds self-hosted alternative)

**Cost mitigation:**
- Embeddings are cached in Redis for 24h keyed on `SHA256(fingerprint_text + model_version)`
- Re-embedding only occurs when a tool definition changes
- For a 500-tool registry with 10% monthly churn, embedding costs are approximately $2–5/month
