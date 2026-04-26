# Dr. Nexus

**Hackathon:** Fulcrum × Hack-Nation @ World Bank Youth Summit 2026
**Stack:** Next.js 15 + FastAPI + Tavily + Supabase + Vercel
**Goal:** Turn a scientific hypothesis into a complete, executable experiment plan (protocol, materials with catalog numbers, budget, timeline, validation) in under 60 seconds.

## Core Differentiator

Unlike ChatGPT/DeepSeek which produce text reports, this system produces **structured, executable plans** with specific catalog numbers, real pricing, and dependency-aware timelines. A multi-agent architecture mirrors real lab delegation, and a Knowledge Garden (PKM) learns from scientist corrections to improve future plans.

## Architecture

- **Frontend:** Next.js 15 on Vercel — Vercel AI SDK, shadcn/ui, Tailwind, Recharts, react-force-graph-2d
- **Backend:** FastAPI (Python) on Railway — LangGraph agent orchestrator, SSE streaming
- **Database:** Supabase — Realtime for live agent updates, pgvector for knowledge embeddings
- **Search:** Tavily API — `/search`, `/extract`, `/research` for literature and protocol discovery
- **LLM:** GPT-4o or Claude (configurable via env)

## Multi-Agent System

| Agent | Role | Key Output |
|-------|------|------------|
| 🔍 Literature Scout | Check if experiment exists, find references | Novelty signal + 1-3 refs |
| 🧪 Protocol Designer | Generate step-by-step methodology | Numbered protocol steps with durations |
| 📦 Materials Agent | Find reagents, catalog numbers, suppliers | Materials table with catalog numbers |
| 💰 Budget Agent | Calculate costs with line items | Budget breakdown table |
| ⏱️ Timeline Agent | Calculate dependencies and schedule | Phased timeline with dependencies |
| ✅ Review Agent | Validate internal consistency | Warnings, consistency checks |
| 🧠 PKM Agent | Extract knowledge nodes from plans | Knowledge graph entries |

### Agent Communication Flow

1. User submits prompt → Orchestrator spawns Literature Scout + Protocol Designer + Materials Agent **in parallel**
2. All agents stream status updates → Supabase Realtime → Frontend shows live progress cards
3. Results collected → Budget Agent + Timeline Agent run (they depend on earlier outputs)
4. Review Agent validates → warnings/errors back to relevant agents
5. Final plan compiled → saved to Supabase
6. PKM Agent extracts insights → Knowledge Garden updated

## Key Conventions

- **Agent system prompts** define: role persona, specific task, required JSON output schema, available data sources, quality constraints
- **Streaming:** SSE (Server-Sent Events) from FastAPI → frontend via Vercel AI SDK
- **Product catalog:** `static/product_catalog.json` — reagents with verified catalog numbers; agents cross-reference this before web search
- **Hallucination guard:** Reagents not in product catalog get flagged as `"Suggested: Verify before ordering"`
- **Knowledge nodes:** Stored in Supabase `knowledge_nodes` table with vector embeddings; corrections become few-shot examples for future generations
- **UI theme:** Dark mode, shadcn/ui components, Tailwind styling

## Environment Variables

```env
SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY
TAVILY_API_KEY
OPENAI_API_KEY / ANTHROPIC_API_KEY
ALLOWED_ORIGINS
MAX_PLAN_SIZE_MB=5
STREAMING_TIMEOUT_SECONDS=120
```

## MVP Priorities

### P0 — Must Have
- Working prompt → plan pipeline with SSE streaming
- Literature QC with Tavily (novelty signal + refs)
- Tabs: Protocol, Materials (with catalog numbers), Budget, Timeline
- Live agent progress cards (3-4 agents visible)

### P1 — Should Have
- Scientist feedback/correction UI
- Knowledge nodes from corrections (Supabase)
- Knowledge graph visualization (react-force-graph)
- Corrections injected as few-shot examples

### P2 — Nice to Have
- Validation tab, Review agent, PDF export, dark mode toggle

## Common Pitfalls

| Problem | Solution |
|---------|----------|
| Agents too slow | 30s timeout per agent, show partial results |
| Hallucinated catalog numbers | Cross-reference `product_catalog.json`, flag unverified |
| Oversized plans | Max 15 protocol steps, 25 materials |
| SSE connection drops | Reconnection logic + "Reconnecting..." toast |
| Knowledge graph clutter | Max 50 visible nodes, filter by experiment type |