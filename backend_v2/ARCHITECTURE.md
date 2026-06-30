# backend_v2 — Architecture & Design Decisions

## 1. Folder & File Overview

```
backend_v2/
├── console.py                  # Interactive CLI to test the chatbot without a web server
├── app/
│   ├── orchestrator.py         # Core state machine (2 modes: IDLE → WORKING)
│   ├── store.py                # In-memory session store (get/reset/delete)
│   ├── config/
│   │   ├── field_specs.py      # Declarative field definitions for 6 resource types
│   │   └── resources.py        # Environment, enterprise, and resource-type menus
│   ├── core/
│   │   ├── collector.py        # Pure Python logic — decides what to ask next (no LLM)
│   │   └── context_builder.py  # Builds minimal LLM context from collection plans
│   ├── llm/
│   │   ├── client.py           # Thin OpenAI wrapper (chat + chat_json)
│   │   ├── format.py           # Asks LLM to phrase a natural-language question
│   │   └── parse.py            # Asks LLM to extract field values from user text
│   ├── models/
│   │   └── state.py            # Dataclass models: Session, Resource, FieldSpec, enums
│   └── prompts/
│       ├── intent.py           # Prompt for initial intent + resource type detection
│       ├── extract.py          # Prompt for field extraction during collection
│       └── format.py           # Prompt for question formatting
```

---

## 2. What Each Module Does

| Module | Responsibility |
|--------|---------------|
| **console.py** | REPL loop for testing — type messages, see bot responses, no web server needed |
| **orchestrator.py** | Routes user messages: IDLE → detect intent & create resources; WORKING → collect fields. ~160 lines |
| **store.py** | Stores sessions in a dict. 30 lines. Will be swapped for DB later |
| **field_specs.py** | Defines every field for every resource type as `FieldSpec` dataclasses with options, validations, dependencies, defaults |
| **resources.py** | Static config: which environments, enterprises, and resource types are available |
| **collector.py** | Determines which fields are askable (resolves dependencies, deduplicates across resources), produces a `CollectionPlan` |
| **context_builder.py** | Constructs focused prompt context from the plan — only includes relevant field specs to minimize tokens |
| **client.py** | Wraps OpenAI API. Two methods: `chat()` for text, `chat_json()` for structured output |
| **format.py** (llm) | Calls LLM to turn a CollectionPlan into a friendly natural-language question |
| **parse.py** | Calls LLM to extract field values from the user's message; also handles initial intent detection |
| **state.py** | Clean data models: `Session` holds a list of `Resource`s, each resource has a status and collected fields |
| **intent.py** | System prompt for the first user message: "what resource do they want?" |
| **extract.py** | System prompt for subsequent messages: "what field values did they provide?" |
| **format.py** (prompts) | System prompt for question generation: "ask about these missing fields naturally" |

---

## 3. Why We Created a New Backend Instead of Fixing the Old One

### Problems with `backend/` (v1)

| Problem | Impact |
|---------|--------|
| **LLM as logic engine** | A single 100-line prompt asks the LLM to extract fields, validate, decide next action, format the reply, AND manage flow control — all at once. Unpredictable and hard to debug. |
| **State explosion** | `StructuredFlow` has 15+ mutable fields, `AgentState` has 10+, `SessionState` adds more. Dozens of interacting variables = combinatorial bugs. |
| **One-resource-at-a-time** | Multi-resource was bolted on after the fact via `batch_handler.py` and queue interleaving. Complex and fragile. |
| **Token waste** | Entire 200-300 line Markdown guides are injected into every LLM call, even for simple field questions. |
| **Monolithic prompts** | LLM follows 15+ rules, handles 6+ `next_action` paths, and produces complex JSON — leading to hallucination. |
| **Handler sprawl** | 12+ tightly-coupled modules (orchestrator, collector, confirmation_handler, batch_handler, structured_flow_handler, pr_handler, field_deriver, response_decorator…) sharing mutable state. |
| **Untestable** | Every code path requires real LLM calls. No separation between deterministic logic and AI. |
| **Only 3 resources** | Supported s3, glue_db, iam. Adding more would mean touching prompts, handlers, state models, and validators. |

### Why a Rewrite Was the Right Call

Fixing v1 would require:
- Rewriting the state model (breaking all handlers)
- Splitting the monolithic prompt (breaking flow control logic)
- Redesigning multi-resource from scratch (breaking batch handler)
- Separating collection logic from LLM (breaking the structured flow)

Every module depends on every other module's internal state. Fixing one thing cascades into rewriting everything else. At that point, a clean-room rewrite is faster and produces better architecture.

---

## 4. Key Design Principles in v2

| Principle | How It's Applied |
|-----------|------------------|
| **LLM does NLU only** | LLM extracts values and phrases questions. Python decides what to ask, when, and in what order. |
| **Multi-resource native** | `CollectionPlan` groups shared fields across N resources. No batch system needed. |
| **Declarative config** | Adding a resource = adding `FieldSpec` entries. No prompt/handler/state changes. |
| **Minimal state** | 2 modes (IDLE, WORKING). One list of resources. One status per resource. |
| **Testable** | `collector.py` is pure logic with zero LLM dependency. LLM layer is thin and mockable. |
| **Token-efficient** | `context_builder.py` passes only relevant field specs to LLM, not entire documents. |

---

## 5. Resource Coverage

| Resource Type | v1 | v2 |
|---------------|----|----|
| S3 Bucket | ✅ | ✅ |
| Glue DB | ✅ | ✅ |
| IAM Role | ✅ | ✅ |
| Resource Policy | ❌ | ✅ |
| SMUS Role | ❌ | ✅ |
| SMUS Project | ❌ | ✅ |
