# Architecture: Enterprise Data Pipeline Automation Platform

## Design Principle

**Repo Agents + Shared Skills/Tools**

Each target repo gets its own agent (own LangGraph graph) with its own flow topology.
Agents share reusable skills (Collector, Generator, Validator, PR Creator) and tools (MCP integrations).

---

## Why This Design?

| Concern | Decision |
|---------|----------|
| Different repos have different flows | Each repo agent owns its graph topology |
| Collection logic is identical across repos | Shared Collector skill — config-driven |
| Code generation differs (YAML vs HCL) | Shared Generator skill — template-driven |
| Validation rules differ per resource | Shared Validator skill — rules from .md |
| PR creation is always the same | Shared PR Creator skill |
| Debugging should be easy | Each agent has explicit named nodes |
| Adding a new repo should be low-effort | New agent graph + reuse all skills |

---

## System Layers

```
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 0: INTENT CLASSIFICATION (Top-Level Router)                       │
│                                                                          │
│  Routes to: PR Workflow | Q&A | Support Ticket | Status Check            │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   │
                                   ▼ (if PR Workflow)
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 1: REPO AGENTS (Each has its own LangGraph sub-graph)            │
│                                                                          │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐            │
│  │  MIW Agent     │  │  MIF Agent     │  │  Future Agent  │            │
│  │  (AWS resources)│  │  (Kafka topics)│  │  (...)         │            │
│  │  Own graph      │  │  Own graph     │  │  Own graph     │            │
│  └────────────────┘  └────────────────┘  └────────────────┘            │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   │ (invokes)
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 2: SHARED SKILLS (Reusable node functions)                        │
│                                                                          │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌──────────┐│
│  │ Collector │ │ Generator │ │ Validator │ │ PR Creator│ │ Confirm  ││
│  └───────────┘ └───────────┘ └───────────┘ └───────────┘ └──────────┘│
└──────────────────────────────────┬───────────────────────────────────────┘
                                   │ (uses)
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 3: TOOLS (MCP Servers + Utilities)                                │
│                                                                          │
│  ┌───────────┐ ┌───────────────┐ ┌───────────┐ ┌───────────┐          │
│  │ GitHub MCP│ │ TF Validate   │ │ RAG Search│ │ Jira MCP  │          │
│  └───────────┘ └───────────────┘ └───────────┘ └───────────┘          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Intent Classifier — 4 Routes

| Intent | Destination | Description |
|--------|-------------|-------------|
| `pr_workflow` | Repo Agent (MIW/MIF/etc.) | User wants to create/modify infrastructure |
| `qa` | Q&A Agent (RAG) | User asking documentation questions |
| `support_ticket` | Ticket Agent (Jira MCP) | User needs help, create Jira ticket |
| `status_check` | Status Agent | User checking PR status or request progress |

---

## Current Scope

**Phase 1: MIW Agent only**

- Single repo: MIW (AWS resource provisioning via YAML)
- 6 resource types: `s3`, `glue_db`, `iam`, `resource_policy`, `smus_project`, `smus_role`
- Output: YAML files committed to MIW repo via PR

**Future Phases:**
- Phase 2: MIF Agent (Kafka topics via Terraform)
- Phase 3: Additional repos as needed
