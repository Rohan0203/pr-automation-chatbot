# Implementation Plan — Incremental Steps

## Philosophy

- Build incrementally, test in console at each step
- Get the graph skeleton working first (hardcoded responses)
- Then replace hardcoded nodes with real LLM calls one by one
- Add MCP tools last (mock them initially)

---

## Phase 1: Graph Skeleton (Console Testable)

### Step 1.1 — Minimal graph with hardcoded nodes

**Goal:** Prove the graph topology works end-to-end.

- [ ] Set up `backend/graph/` and `backend/agents/miw/`
- [ ] Define `MIWState` TypedDict
- [ ] Create MIW graph with all nodes as pass-through stubs
- [ ] Wire edges and conditional routing
- [ ] Use `InMemorySaver` (swap to Postgres later)
- [ ] Test: invoke graph, see it traverse all nodes correctly

**Test in console:**
```python
python -m backend.agents.miw.graph
# Should print: understand → collect_common → plan → collect_resource → generate → validate → confirm → create_pr → summarize
```

### Step 1.2 — Add state transitions

- [ ] Make `collect_common` actually check `common_collection_complete`
- [ ] Make routing work (loops back when incomplete, moves forward when complete)
- [ ] Make task loop work (processes multiple resources sequentially)
- [ ] Test with hardcoded state mutations

---

## Phase 2: Skills with LLM (One at a Time)

### Step 2.1 — Collector Skill (real LLM)

- [ ] Create `backend/skills/collector.py`
- [ ] Write `common_collection.md` for MIW
- [ ] Wire `collect_common` node to use Collector Skill
- [ ] Test: chat in console, see it ask for env/enterprise/subgroup

### Step 2.2 — Generator Skill (real LLM)

- [ ] Create `backend/skills/generator.py`
- [ ] Write ONE resource config first: `s3/generation.md`
- [ ] Wire `generate` node to use Generator Skill
- [ ] Test: provide fields, see it generate YAML

### Step 2.3 — Validator Skill (real LLM + rules)

- [ ] Create `backend/skills/validator.py`
- [ ] Write `s3/validation.md`
- [ ] Wire `validate` node
- [ ] Test: pass good/bad YAML, see pass/fail results

### Step 2.4 — Confirm Skill (interrupt/resume)

- [ ] Create `backend/skills/confirm.py`
- [ ] Use LangGraph `interrupt_before` on confirm node
- [ ] Test: graph pauses, show code to user, resume on approval

---

## Phase 3: Tools & MCP

### Step 3.1 — GitHub MCP (read operations)

- [ ] Create `backend/tools/github_mcp.py`
- [ ] Implement: read_file_tree, read_file, search_files
- [ ] Wire into Generator (for repo context) and Validator (for dupe check)

### Step 3.2 — GitHub MCP (write operations)

- [ ] Implement: create_branch, commit_files, create_pr
- [ ] Wire into PR Creator skill
- [ ] Test: actually create a PR in a test repo

### Step 3.3 — RAG

- [ ] Set up vector store (pgvector or in-memory for POC)
- [ ] Index: existing repo examples, architecture docs
- [ ] Wire into Generator for few-shot examples

---

## Phase 4: Remaining Resources

### Step 4.1 — Add all 6 resource configs

- [ ] `glue_db/` — collection.md, generation.md, validation.md
- [ ] `iam/` — collection.md, generation.md, validation.md
- [ ] `resource_policy/` — collection.md, generation.md, validation.md
- [ ] `smus_project/` — collection.md, generation.md, validation.md
- [ ] `smus_role/` — collection.md, generation.md, validation.md

(These are just config files — no code changes needed!)

---

## Phase 5: Intent Classifier & Other Routes

### Step 5.1 — Top-level graph with intent classification

- [ ] Create `backend/graph/main_graph.py`
- [ ] Intent classifier node (LLM-based routing)
- [ ] Route to MIW agent for `pr_workflow`
- [ ] Stub Q&A, Support Ticket, Status Check routes

### Step 5.2 — Q&A Agent

- [ ] RAG-based Q&A (search docs, return answer)
- [ ] No PR creation, just conversational

### Step 5.3 — Support Ticket Agent

- [ ] Collect issue description
- [ ] Create Jira ticket via MCP

---

## Phase 6: Production Hardening

- [ ] Swap `InMemorySaver` → `AsyncPostgresSaver`
- [ ] Add LangSmith tracing
- [ ] Add error handling and retry logic
- [ ] Multi-tenant (thread-per-conversation)
- [ ] WebSocket + REST API support
- [ ] Rate limiting on MCP calls

---

## What We Build First (Immediate Next Steps)

```
1. MIW graph skeleton (all stubs)           → test graph topology
2. Collector skill + common_collection.md   → test conversational collection
3. Generator skill + s3/generation.md       → test code generation
4. Validator skill + s3/validation.md       → test validation
5. Wire it all together                     → end-to-end console test
```

After step 5, we have a working prototype that can:
- Understand "create an S3 bucket for protein team"
- Ask clarifying questions
- Generate YAML
- Validate it
- Show it to user for approval

No PR creation yet (that needs GitHub MCP), but the core intelligence works.
