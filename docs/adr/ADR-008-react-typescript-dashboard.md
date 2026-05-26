# ADR-008: React + TypeScript + Tailwind for the Governance Dashboard

**Status:** Accepted  
**Date:** 2025-05  
**Deciders:** AI Platform Team

---

## Context

Phase 3 adds the governance dashboard — the primary UI for non-technical stakeholders (governance leads, product managers, AI platform managers) to review conflicts, approve tool registrations, and track registry health.

The dashboard requires:
- A complex, interactive force-directed graph (conflict map) with D3.js
- Real-time data polling / live updates on analysis run status
- A rich table/filter UI for the conflict queue and registry view
- Responsive layout for use on laptops and external monitors
- An approval workflow with form interactions

The choice of frontend stack determines developer ergonomics, long-term maintainability, and the available component ecosystem.

---

## Decision Drivers

- **D3.js integration:** The conflict map is a force-directed graph — D3.js is the industry standard for this. The frontend must integrate D3.js cleanly (React refs + effect pattern works well).
- **Type safety:** Dashboard interacts with complex API response shapes (tools, conflicts, recommendations). TypeScript catches interface mismatches at compile time.
- **Styling velocity:** The dashboard needs a polished, professional look that enterprise governance teams trust. Tailwind CSS provides design system discipline without a component library lock-in.
- **Ecosystem:** React's ecosystem for tables, forms, query management, and routing is mature and well-documented.
- **Team familiarity:** React + TypeScript is the most widely known frontend stack across enterprise engineering teams.

---

## Options Considered

| Option | D3.js Integration | Type Safety | Ecosystem | Notes |
|---|---|---|---|---|
| **React + TypeScript + Tailwind** | ✅ Via refs/effects | ✅ TypeScript | ✅ Largest | Industry standard |
| Vue 3 + TypeScript + Tailwind | ✅ Similar | ✅ TypeScript | ✅ Good | Good alternative, smaller ecosystem |
| SvelteKit + TypeScript | ✅ Direct DOM access | ✅ TypeScript | ⚠️ Smaller | Excellent DX but niche in enterprise |
| Angular + TypeScript | ✅ Via ElementRef | ✅ Strict | ✅ Good | Heavy framework, slower iteration |
| Server-rendered (Jinja2 + HTMX) | ⚠️ Limited | ❌ | ⚠️ Limited | Would not support conflict map interactivity |

---

## Decision

**React 18 + TypeScript 5 + Tailwind CSS 3 + D3.js 7.**

Supporting library choices:

| Library | Purpose | Rationale |
|---|---|---|
| TanStack Query (React Query) v5 | Server state management | Polling, caching, optimistic updates |
| React Router v6 | Client-side routing | Standard, well-documented |
| Vite 5 | Build tooling | Fast HMR, tree-shaking |
| Vitest | Unit testing | Native Vite integration |
| Playwright | E2E testing | Cross-browser, reliable selectors |
| shadcn/ui | Base components | Tailwind-compatible, owned — no vendor lock-in |

**D3.js integration pattern:**

The conflict map uses D3 directly via React refs:
```typescript
const svgRef = useRef<SVGSVGElement>(null);

useEffect(() => {
  if (!svgRef.current || !data) return;
  const simulation = d3.forceSimulation(data.nodes)
    .force('link', d3.forceLink(data.links))
    .force('charge', d3.forceManyBody().strength(-300))
    .force('center', d3.forceCenter(width / 2, height / 2));
  // ... D3 draws directly into the SVG element
}, [data]);
```

React manages component lifecycle and routing; D3 owns the SVG rendering. This avoids the awkward React-D3 reconciler conflict and is the recommended pattern for complex D3 visualizations.

---

## Consequences

**Positive:**
- TypeScript catches API contract mismatches at compile time — especially valuable as the API evolves
- D3.js integration via refs is clean and proven for force-directed graphs
- Tailwind provides a consistent design system across all views
- TanStack Query handles polling for analysis run status cleanly
- React ecosystem provides solutions for complex table/filter UI (TanStack Table)

**Negative:**
- React bundle size is larger than Svelte or HTMX alternatives
- Force-directed D3.js graphs require careful performance optimization for > 500 nodes (Phase 4: WebGL renderer via Sigma.js as fallback)
- React + TypeScript setup complexity vs. simpler alternatives

**Performance threshold for conflict map:**
- Up to 200 nodes (tools): standard D3.js SVG rendering
- 200–1,000 nodes: switch to canvas rendering with D3
- > 1,000 nodes: Sigma.js (WebGL-accelerated) as fallback (Phase 4)
