# ADR-006: English-Only Tool Descriptions for v1

**Status:** Accepted  
**Date:** 2025-05  
**Deciders:** AI Platform Team  
**PRD Reference:** Open Question #2 (Decided)

---

## Context

MCP tool descriptions are natural language text used by LLMs for routing. Tools at multinational enterprises may have descriptions in multiple languages (English, Spanish, French, Japanese, etc.). MTGS's conflict detection relies on semantic similarity — and semantic similarity across languages requires multilingual embedding models.

The question is whether to support multilingual descriptions in v1 or defer it.

---

## Decision Drivers

- **Embedding model quality:** Multilingual embedding models (`multilingual-e5-large`, `Cohere embed-multilingual-v3`) have lower quality on English-to-English similarity than `text-embedding-3-large` on English-only content
- **Target market:** Initial customers are English-first enterprises — the US/EU enterprise AI platform teams deploying MCP at scale
- **Complexity:** Cross-language conflict detection requires either: (a) translating all descriptions to English before embedding, or (b) using multilingual models consistently. Both add complexity.
- **Recommendation engine:** The Claude-powered recommendation engine generates English rewrites. Non-English outputs require prompt engineering and validation.
- **v1 timeline:** Phase 1+2 scope is already ambitious. Multilingual support would delay delivery.

---

## Decision

**English-only for v1.** Tool descriptions must be in English to be processed by MTGS.

A validation warning (not a hard error) is shown when non-English content is detected in a tool description. This uses `langdetect` (simple heuristic, not a blocker).

Multilingual support is planned for Phase 4, using one of:
- Multilingual embeddings (Cohere embed-multilingual-v3 or `multilingual-e5-large`)
- Translation preprocessing (Azure Translator → normalize to English → embed)

---

## Consequences

**Positive:**
- `text-embedding-3-large` provides maximum semantic similarity quality for English content
- Simpler system — no need for language detection, translation, or multilingual model management
- Recommendation engine generates high-quality English rewrites without multilingual prompt complexity

**Negative:**
- Excludes non-English MCP deployments from v1
- Creates a technical debt item for Phase 4

**Non-English tool handling in v1:**
- MTGS will still register non-English tools (no hard block)
- Stage 3 semantic analysis will run but quality is undefined/reduced
- A `language_warning` flag is included in analysis results when non-English content is detected
- Users are informed via dashboard that multilingual support is planned
