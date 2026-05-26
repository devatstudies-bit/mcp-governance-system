# ADR-009: Claude Sonnet for Routing Simulation and Recommendation Generation

**Status:** Accepted  
**Date:** 2025-05  
**Deciders:** AI Platform Team

---

## Context

MTGS needs an LLM for two distinct roles:

1. **Routing simulation (Stage 4):** Given a set of tool definitions and a user query, which tool would an LLM select? This simulates realistic LLM tool-routing behavior to detect `INTENT_AMBIGUITY` and `SCOPE_BLEED` conflicts.

2. **Recommendation generation:** Given a detected conflict, generate specific, actionable fixes — rewritten descriptions, renamed tools, scope narrowings — with before/after diffs and rationale.

The LLM choice for these roles must be justified on quality, tool-use fidelity, and practical integration constraints.

---

## Decision Drivers

**For routing simulation:**
- **Tool-use fidelity:** The simulation is only valid if the LLM's behavior in simulation approximates real LLM tool selection. If we simulate with GPT-4o but customers use Claude, the simulation is less representative.
- **Consistency:** Using the same model family for simulation and for production means the routing simulation is self-referential — it predicts how Claude routes, which is directly applicable for Claude-based agents.
- **Stability at temperature=0:** Must produce consistent routing decisions across trials.

**For recommendation generation:**
- **Instruction following:** Must produce structured JSON output with specific before/after text, not vague suggestions.
- **Domain understanding:** Must understand MCP tool design patterns, LLM routing mechanics, and what makes a good tool description.
- **Context window:** Must fit the full tool set (potentially 50+ tool definitions) in context when generating recommendations.

---

## Options Considered

| Model | Routing Fidelity | Instruction Following | Context | Cost | Notes |
|---|---|---|---|---|---|
| **Claude Sonnet 4.6** | ✅ Best (Anthropic tools) | ✅ Excellent | ✅ 200K tokens | $$ | Our choice |
| Claude Opus 4.7 | ✅ Excellent | ✅ Best | ✅ 200K tokens | $$$$ | Overkill for routing sim |
| GPT-4o (Azure OpenAI) | ✅ Excellent | ✅ Very good | ✅ 128K tokens | $$$ | Good alternative |
| GPT-4o mini | ⚠️ Good | ⚠️ Good | ✅ 128K tokens | $ | Lower quality recommendations |
| Llama 3.1 70B (self-hosted) | ⚠️ Good | ⚠️ Moderate | ⚠️ 128K tokens | $ (GPU) | Air-gapped option (Phase 4) |

---

## Decision

**Claude Sonnet 4.6 (`claude-sonnet-4-6`) via the Anthropic API** for both routing simulation and recommendation generation.

**Rationale:**
1. Most enterprise MCP deployments in 2025 use Claude as the underlying LLM. Routing simulation with Claude is therefore directly predictive of real routing behavior — not just approximate.
2. Claude Sonnet's instruction-following quality reliably produces structured JSON recommendations with real before/after text rather than vague advice.
3. The 200K token context window can accommodate large tool registries (500 tools × ~200 tokens each = 100K tokens, fitting comfortably).
4. Sonnet is positioned at the right cost/quality tradeoff — Opus would be overkill for routing simulation (which just needs a tool name selection), and Haiku is too limited for nuanced recommendation generation.

**Model ID pinning:** The model is configurable via environment. Default is `claude-sonnet-4-6`. This allows customers to pin to a specific version for stability, or upgrade to newer models as they become available.

---

## Consequences

**Positive:**
- Routing simulation is most accurate when the simulation model matches the customer's production LLM
- Claude Sonnet's structured output quality produces actionable, specific recommendations (actual rewritten text, not "consider improving your description")
- Single API vendor for LLM calls (Anthropic only) simplifies integration

**Negative:**
- Anthropic API key required; customers without an Anthropic relationship must create one
- Routing simulation is biased toward Claude routing behavior — if a customer uses GPT-4 for their agent, the simulation is less representative (mitigated by making the model configurable)
- Rate limits on Anthropic API constrain simulation worker concurrency (addressed by the separate `simulation` Celery queue with concurrency=2 per ADR-004)

**Air-gapped deployments (Phase 4):**
A self-hosted LLM mode is planned for Phase 4 using Llama 3.1 70B or Qwen 2.5 72B. The LLM client is behind an interface, so swapping the backend requires only a configuration change.

**Temperature policy:**
- Routing simulation: `temperature=0.0` — deterministic, reproducible
- Recommendation generation: `temperature=0.3` — slight creativity for generating diverse, context-appropriate rewrite options
