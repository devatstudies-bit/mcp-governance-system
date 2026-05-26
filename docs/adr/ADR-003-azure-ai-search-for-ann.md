# ADR-003: Azure AI Search for ANN Vector Search (over pgvector)

**Status:** Accepted  
**Date:** 2025-05  
**Deciders:** AI Platform Team

---

## Context

Stage 3 of the conflict detection pipeline requires finding the top-K most semantically similar tools to a candidate from the registry. With registries potentially reaching 10,000 tools, brute-force O(N) cosine similarity on every registration would be too slow.

Two main options exist: a dedicated vector database/search service, or the pgvector PostgreSQL extension. The PRD originally specified pgvector, but the infrastructure reality was evaluated during implementation.

---

## Decision Drivers

- **Query latency:** ANN search must complete in < 3 seconds for up to 10,000 tools (NFR-PERF-001)
- **Operational complexity:** Fewer services = lower operational burden
- **Azure-native deployment:** Enterprise customers run on Azure; managed services reduce ops
- **Top-K recall quality:** ANN must find true nearest neighbors with > 95% recall
- **Index management:** Re-indexing on tool updates must be handled without downtime

---

## Options Considered

### Option A: pgvector (PostgreSQL extension)

```sql
CREATE INDEX ON tools USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
SELECT id, name, 1 - (embedding <=> $1) AS similarity FROM tools ORDER BY similarity DESC LIMIT 20;
```

**Pros:** Co-located with registry DB, single service to manage, transactional updates  
**Cons:** Requires pgvector extension availability on managed PostgreSQL, ANN tuning (lists parameter) needs calibration as registry grows, performance degrades without proper VACUUM on updates

### Option B: Azure AI Search

Managed vector search service with HNSW indexing.

**Pros:** Purpose-built for ANN, managed scaling, no index tuning, integrates with Azure ecosystem  
**Cons:** Separate service to manage, adds network hop, eventual consistency (embedding update vs. search availability)

### Option C: Pinecone / Weaviate / Qdrant

Dedicated vector databases.

**Pros:** Purpose-built, high performance  
**Cons:** Additional vendor, not Azure-native, another managed service, overkill for ≤10K vectors

---

## Decision

**Azure AI Search** for ANN vector search in production.

pgvector remains available as an option for self-hosted / smaller deployments where Azure AI Search is not available. The `AzureSearchClient` protocol interface means the backend can be swapped.

Rationale for preferring Azure AI Search over pgvector in the primary deployment:
1. Azure AI Search's HNSW index provides consistent ANN latency without manual tuning as the registry grows
2. Managed service eliminates the need to tune `ivfflat.lists` as tool count grows (the formula `sqrt(n)` requires periodic index rebuilds)
3. Azure Flexible Server for PostgreSQL is the planned production DB — adding pgvector to a managed PostgreSQL service has additional provisioning steps; Azure AI Search is already managed
4. All enterprise customers are on Azure — consolidating to Azure services reduces the vendor surface

---

## Consequences

**Positive:**
- ANN latency stays sub-second at 10,000 tools without manual index management
- Managed scaling — Azure AI Search auto-scales the index
- Native Azure RBAC for access control
- HNSW index provides higher recall than IVFFlat at equivalent latency

**Negative:**
- Additional Azure service to provision and pay for
- Network hop for every Stage 3 search (~5–20ms latency overhead)
- Eventual consistency: tool embedding updates are not immediately queryable (typically < 1 second propagation, acceptable for our use case)
- Not available for air-gapped deployments (Phase 4 plans pgvector as a fallback for this case)

**Embedding client interface (future-proofing):**

```python
class EmbeddingSearchProtocol(Protocol):
    async def embed(self, text: str) -> list[float]: ...
    async def search_nearest(self, embedding: list[float], top_k: int) -> list[dict]: ...
    async def upsert(self, tool_id: str, embedding: list[float]) -> None: ...
    async def delete(self, tool_id: str) -> None: ...
```

Any implementation (Azure AI Search, pgvector, Qdrant) can satisfy this interface.
