 # Production Architecture: Enterprise Data Pipeline Automation Platform
 
## Executive Summary
 
This document defines the production-ready architecture for an enterprise multi-agent platform that automates data pipeline provisioning through conversational AI. The platform handles end-to-end infrastructure creation — from Kafka topics to Glue jobs to IAM policies — across multiple repos, using governed agents with proper separation of reasoning, authorization, and execution.
 
---
 
## 1. Architecture Zones (Aligned with Enterprise Vision)
 
```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         ENTERPRISE AI PLATFORM                                   │
├──────────┬───────────────────────────────────────────┬──────────────────────────┤
│  ZONE 1  │              ZONE 2                       │         ZONE 3           │
│  User    │       AI Control Plane                    │   Governed Execution     │
│  Layer   │  (Reasoning + Orchestration)              │   (MCP Servers/Tools)    │
├──────────┼───────────────────────────────────────────┼──────────────────────────┤
│          │                                           │                          │
│ React UI │  AI Gateway → Intent Router               │   GitHub MCP Server      │
│ Chat App │       ↓                                   │   Terraform MCP Server   │
│ SSO/Auth │  Super-Agent (LangGraph)                  │   AWS MCP Server         │
│          │       ↓                                   │   Jira MCP Server        │
│          │  Domain Agents (Sub-Graphs)               │   Vault MCP Server       │
│          │    • Topic Agent                          │                          │
│          │    • KMS Agent                            │                          │
│          │    • Glue Agent                           │                          │
│          │    • IAM/S3 Agent                         │                          │
│          │    • Pipeline Agent                       │                          │
│          │                                           │                          │
└──────────┴───────────────────────────────────────────┴──────────────────────────┘
```
 
---
 
## 2. LangGraph in Production — How to Use It Properly
 
### 2.1 Production Deployment Model
 
```
┌─────────────────────────────────────────────────────────────────┐
│                  LangGraph Platform (Production)                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────┐    ┌────────────────────┐                     │
│  │ LangGraph    │    │  Checkpointer      │                     │
│  │ Cloud / Self │    │  (PostgreSQL)       │  ← NOT InMemory    │
│  │ Hosted       │    └────────────────────┘                     │
│  └──────┬───────┘                                                │
│         │            ┌────────────────────┐                     │
│         ├───────────→│  LangGraph Store   │  ← Long-term memory │
│         │            │  (Vector + KV)     │                     │
│         │            └────────────────────┘                     │
│         │            ┌────────────────────┐                     │
│         ├───────────→│  Human-in-Loop     │  ← Approvals        │
│         │            │  (interrupt/resume) │                     │
│         │            └────────────────────┘                     │
│         │            ┌────────────────────┐                     │
│         └───────────→│  Cron / Scheduled  │  ← Retry, cleanup   │
│                      │  Tasks             │                     │
│                      └────────────────────┘                     │
└─────────────────────────────────────────────────────────────────┘
```
 
**Key Production Patterns:**
 
| POC (Current) | Production (Target) |
|---|---|
| `InMemorySaver` | `PostgresSaver` or `LangGraph Cloud Checkpointer` |
| Single graph, single session | Multi-tenant, thread-per-conversation |
| WebSocket only | REST API + WebSocket + Webhook callbacks |
| In-process state | Durable state with TTL and archival |
| No retry | Built-in retry with exponential backoff |
| No observability | LangSmith tracing + OpenTelemetry |
 
### 2.2 LangGraph Production Features You MUST Use
 
```python
# 1. PostgreSQL Checkpointer (durable state)
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
 
checkpointer = AsyncPostgresSaver.from_conn_string(
    "postgresql://user:pass@host:5432/langgraph_state"
)
 
# 2. LangGraph Store (cross-thread memory + RAG)
from langgraph.store.postgres import AsyncPostgresStore
 
store = AsyncPostgresStore.from_conn_string(
    "postgresql://user:pass@host:5432/langgraph_store"
)
# Store indexes embeddings automatically for semantic retrieval
 
# 3. Subgraph Composition (multi-agent)
from langgraph.graph import StateGraph
 
# Each domain agent is its own compiled subgraph
topic_agent_graph = build_topic_agent()
kms_agent_graph = build_kms_agent()
glue_agent_graph = build_glue_agent()
 
# Super-agent composes them
super_graph = StateGraph(SuperState)
super_graph.add_node("topic_agent", topic_agent_graph)
super_graph.add_node("kms_agent", kms_agent_graph)
super_graph.add_node("glue_agent", glue_agent_graph)
 
# 4. Human-in-the-Loop (approvals before PR creation)
graph.add_node("create_pr", create_pr_node)
# interrupt BEFORE destructive actions
compiled = graph.compile(interrupt_before=["create_pr"], checkpointer=checkpointer)
 
# 5. Streaming (token-by-token to UI)
async for event in graph.astream_events(input, config, version="v2"):
    if event["event"] == "on_chat_model_stream":
        yield event["data"]["chunk"].content
```
 
### 2.3 LangGraph Cloud vs Self-Hosted
 
| Aspect | LangGraph Cloud | Self-Hosted (K8s) |
|---|---|---|
| Deployment | Managed by LangChain | Your infra |
| Scaling | Auto-scales | HPA on K8s |
| Checkpointing | Built-in durable | You manage Postgres |
| Cron jobs | Built-in | K8s CronJobs |
| Auth | API keys + OAuth | Your IAM |
| Cost | Per-invocation | Infra cost |
| **Recommendation** | For faster time-to-market | For enterprise compliance |
 
**For enterprise with SSO/governance requirements → Self-hosted on K8s with LangGraph SDK.**
 
---
 
## 3. AWS AgentCore + LangGraph — Can You Use It?
 
### 3.1 What is AWS AgentCore?
 
AgentCore is AWS's managed runtime for AI agents. It provides:
- **Agent Gateway** — API endpoint management, auth, throttling
- **Memory** — Managed conversation + semantic memory (DynamoDB + OpenSearch)
- **Tools** — Managed tool execution with IAM-scoped permissions
- **Observability** — CloudWatch integration
- **Guardrails** — Content filtering via Bedrock Guardrails
 
### 3.2 Can You Combine AgentCore with LangGraph?
 
**Yes, but with a clear separation of concerns:**
 
```
┌─────────────────────────────────────────────────────────────────┐
│                                                                   │
│   AgentCore provides:          LangGraph provides:               │
│   ─────────────────────        ──────────────────────            │
│   • API Gateway / Auth         • Graph orchestration             │
│   • Managed Memory Store       • State machine logic             │
│   • Tool Authorization         • Multi-agent composition         │
│   • Guardrails                 • Human-in-the-loop               │
│   • Observability infra        • Interrupt/resume patterns       │
│   • Scaling runtime            • Conditional routing             │
│                                • Streaming                        │
│                                                                   │
│   USE AgentCore AS THE         USE LangGraph AS THE              │
│   RUNTIME + INFRA LAYER        ORCHESTRATION FRAMEWORK           │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```
 
### 3.3 Integration Pattern
 
```python
# Option A: LangGraph as the Agent inside AgentCore
# AgentCore handles: auth, memory persistence, tool auth
# LangGraph handles: the actual reasoning graph
 
# Your LangGraph graph runs INSIDE an AgentCore-managed container
# AgentCore's memory → feeds into LangGraph state on each invocation
# AgentCore's tools → wrapped as LangGraph ToolNodes
 
# Option B: LangGraph Self-Hosted + AgentCore for specific services
# Use AgentCore's Memory API standalone (for conversation persistence)
# Use AgentCore's Code Interpreter tool (for dynamic code gen)
# Use LangGraph for everything else
 
# Recommended: Option A for full enterprise governance
```
 
### 3.4 Decision Matrix
 
| If your priority is... | Use |
|---|---|
| Maximum AWS integration (Bedrock, IAM, CloudWatch) | AgentCore + LangGraph inside |
| Maximum orchestration flexibility | LangGraph self-hosted + Postgres |
| Fastest to production with governance | AgentCore as runtime, LangGraph as framework |
| Multi-cloud / vendor neutral | LangGraph Cloud or self-hosted on K8s |
 
**My Recommendation for your use case:** Given you're already on Azure OpenAI and likely multi-cloud, go with **LangGraph self-hosted on K8s** with a proper PostgreSQL backend. Use MCP servers (not AgentCore tools) for the execution layer since MCP gives you vendor-neutral tool governance that matches your architecture diagram.
 
---
 
## 4. Complete Production Architecture
 
### 4.1 System Architecture Diagram
 
```
                            ┌──────────────────────┐
                            │    React Chat App    │
                            │  (SSO via Azure AD)  │
                            └──────────┬───────────┘
                                       │ WebSocket + REST
                            ┌──────────▼───────────┐
                            │    AI GATEWAY        │
                            │  ─────────────────   │
                            │  • Auth (JWT/SSO)    │
                            │  • Rate Limiting     │
                            │  • Request Logging   │
                            │  • Guardrails        │
                            │  • Session Mgmt      │
                            └──────────┬───────────┘
                                       │
                    ┌──────────────────▼──────────────────┐
                    │         INTENT CLASSIFIER            │
                    │    (LLM-based Router Node)           │
                    │                                      │
                    │  Classifies into:                    │
                    │  • pipeline_provisioning             │
                    │  • documentation_qa                  │
                    │  • support_ticket                    │
                    │  • general_inquiry                   │
                    └───┬──────────┬──────────┬───────────┘
                        │          │          │
          ┌─────────────▼┐   ┌────▼────┐   ┌─▼──────────────┐
          │ SUPER-AGENT  │   │ Q&A     │   │ TICKET         │
          │ (Pipeline    │   │ Agent   │   │ CREATION       │
          │  Orchestrator)│   │ (RAG)  │   │ Agent          │
          └──────┬───────┘   └─────────┘   └────────────────┘
                 │
    ┌────────────▼─────────────────────────────────────┐
    │           TASK DECOMPOSER                         │
    │   "Ingest ERP data to raw layer" decomposes to: │
    │                                                   │
    │   1. Kafka Topic Creation    → Topic Agent       │
    │   2. KMS Key Creation        → KMS Agent         │
    │   3. S3 Bucket + IAM Policy  → AWS Resource Agent│
    │   4. Glue DB + Table         → Glue Agent        │
    │   5. Glue Job (ETL)          → Pipeline Agent    │
    │                                                   │
    │   Determines dependency order:                    │
    │   KMS → Topic → S3 → GlueDB → GlueJob          │
    └──────────────────────────────────────────────────┘
                 │
    ┌────────────▼─────────────────────────────────────┐
    │      GENERALIZED INPUT COLLECTOR                  │
    │                                                   │
    │  Common fields across ALL agents:                 │
    │  • environment (dev/prod)                         │
    │  • enterprise/business_unit                       │
    │  • subgroup/team                                  │
    │  • source_system                                  │
    │  • data_classification (PII/non-PII)             │
    │                                                   │
    │  Collects ONCE, distributes to all sub-agents    │
    └──────────────────────────────────────────────────┘
                 │
    ┌────────────▼─────────────────────────────────────┐
    │         DOMAIN AGENT EXECUTION                    │
    │                                                   │
    │  Each agent is a LangGraph SubGraph:             │
    │                                                   │
    │  ┌─────────────┐  ┌─────────────┐               │
    │  │ Topic Agent │  │  KMS Agent  │               │
    │  │ (SubGraph)  │  │ (SubGraph)  │               │
    │  │             │  │             │               │
    │  │ normalize   │  │ normalize   │               │
    │  │ collect     │  │ collect     │               │
    │  │ plan        │  │ plan        │               │
    │  │ render_tf   │  │ render_tf   │               │
    │  │ create_pr   │  │ create_pr   │               │
    │  └─────────────┘  └─────────────┘               │
    │                                                   │
    │  ┌─────────────┐  ┌─────────────┐               │
    │  │ Glue Agent  │  │  IAM Agent  │               │
    │  │ (SubGraph)  │  │ (SubGraph)  │               │
    │  │             │  │             │               │
    │  │ normalize   │  │ normalize   │               │
    │  │ collect     │  │ collect     │               │
    │  │ plan        │  │ plan        │               │
    │  │ render_yaml │  │ render_tf   │               │
    │  │ create_pr   │  │ create_pr   │               │
    │  └─────────────┘  └─────────────┘               │
    │                                                   │
    └──────────────────────────────────────────────────┘
                 │
    ┌────────────▼─────────────────────────────────────┐
    │     MCP GOVERNANCE LAYER (Tool Execution)        │
    │                                                   │
    │  MCP Registry:                                    │
    │  • Tool discovery & registration                  │
    │  • Policy enforcement (who can call what)         │
    │  • Audit logging (every tool invocation)          │
    │  • Rate limiting per agent                        │
    │                                                   │
    │  MCP Servers:                                     │
    │  ┌──────────┐ ┌──────────┐ ┌──────────┐         │
    │  │ GitHub   │ │Terraform │ │ AWS API  │         │
    │  │ MCP      │ │ Validate │ │ MCP      │         │
    │  │ Server   │ │ MCP      │ │ Server   │         │
    │  └──────────┘ └──────────┘ └──────────┘         │
    │                                                   │
    └──────────────────────────────────────────────────┘
```
 
### 4.2 LangGraph Graph Structure (Production)
 
```python
# Top-level Super Graph
SuperGraph:
    ├── intent_classifier          # Routes to correct workflow
    ├── pipeline_provisioning      # SubGraph (the main workflow)
    │   ├── understand_request     # LLM understands full ask
    │   ├── decompose_tasks        # Breaks into sub-tasks with dependencies
    │   ├── collect_common_inputs  # Shared fields (env, enterprise, etc.)
    │   ├── execute_agents         # Fan-out to domain agents
    │   │   ├── topic_agent        # SubGraph (your current POC, evolved)
    │   │   ├── kms_agent          # SubGraph
    │   │   ├── glue_agent         # SubGraph
    │   │   ├── iam_agent          # SubGraph
    │   │   └── s3_agent           # SubGraph
    │   ├── aggregate_results      # Collect all PRs/outcomes
    │   └── present_summary        # Final response to user
    ├── documentation_qa           # SubGraph (RAG-based Q&A)
    └── support_ticket             # SubGraph (Jira integration)
```
 
---
 
## 5. Where RAG vs DB — Context & Conversation Strategy
 
### 5.1 Complete Data Architecture
 
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        DATA & CONTEXT LAYER                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐     │
│  │                    PostgreSQL (Primary DB)                            │     │
│  │                                                                       │     │
│  │  ┌───────────────────┐  ┌───────────────────┐  ┌─────────────────┐ │     │
│  │  │ Conversation      │  │ Session State     │  │ Audit Log       │ │     │
│  │  │ History           │  │ (Checkpoints)     │  │                 │ │     │
│  │  │                   │  │                   │  │ • Who ran what  │ │     │
│  │  │ • thread_id       │  │ • LangGraph       │  │ • When          │ │     │
│  │  │ • user_id         │  │   checkpoint      │  │ • Outcome       │ │     │
│  │  │ • messages[]      │  │   data            │  │ • PR URLs       │ │     │
│  │  │ • created_at      │  │ • Pending state   │  │                 │ │     │
│  │  │ • metadata        │  │ • Interrupt data  │  │                 │ │     │
│  │  └───────────────────┘  └───────────────────┘  └─────────────────┘ │     │
│  │                                                                       │     │
│  │  ┌───────────────────┐  ┌───────────────────┐                       │     │
│  │  │ Task Registry     │  │ Agent Config      │                       │     │
│  │  │                   │  │                   │                       │     │
│  │  │ • task_id         │  │ • agent_name      │                       │     │
│  │  │ • parent_task_id  │  │ • repo_url        │                       │     │
│  │  │ • agent_assigned  │  │ • required_fields │                       │     │
│  │  │ • status          │  │ • templates       │                       │     │
│  │  │ • dependencies    │  │ • validation_rules│                       │     │
│  │  │ • outputs         │  │ • mcp_tools       │                       │     │
│  │  └───────────────────┘  └───────────────────┘                       │     │
│  └─────────────────────────────────────────────────────────────────────┘     │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐     │
│  │              VECTOR STORE (RAG) — pgvector or Pinecone               │     │
│  │                                                                       │     │
│  │  ┌───────────────────────────────────────────────────────────────┐   │     │
│  │  │  Collection: "pipeline_architecture"                           │   │     │
│  │  │  ──────────────────────────────────────────                    │   │     │
│  │  │  • Data pipeline architecture docs                             │   │     │
│  │  │  • What components exist (Kafka, Glue, S3, etc.)              │   │     │
│  │  │  • When each component is needed                               │   │     │
│  │  │  • Dependency graph between components                         │   │     │
│  │  │  • Organization-specific conventions                           │   │     │
│  │  └───────────────────────────────────────────────────────────────┘   │     │
│  │                                                                       │     │
│  │  ┌───────────────────────────────────────────────────────────────┐   │     │
│  │  │  Collection: "repo_knowledge"                                  │   │     │
│  │  │  ──────────────────────────────────────────                    │   │     │
│  │  │  • Repo README files (how to contribute)                       │   │     │
│  │  │  • Existing .tf / .yaml examples from each repo               │   │     │
│  │  │  • PR templates and conventions                                │   │     │
│  │  │  • Module documentation (Terraform modules)                    │   │     │
│  │  │  • Naming conventions per repo                                 │   │     │
│  │  └───────────────────────────────────────────────────────────────┘   │     │
│  │                                                                       │     │
│  │  ┌───────────────────────────────────────────────────────────────┐   │     │
│  │  │  Collection: "organizational_context"                          │   │     │
│  │  │  ──────────────────────────────────────────                    │   │     │
│  │  │  • Source systems catalog (ERP, CRM, etc.)                    │   │     │
│  │  │  • Enterprise/team/subgroup hierarchy                          │   │     │
│  │  │  • Data classification policies                                │   │     │
│  │  │  • Compliance requirements (GDPR, PII handling)               │   │     │
│  │  │  • Historical decisions and patterns                           │   │     │
│  │  └───────────────────────────────────────────────────────────────┘   │     │
│  │                                                                       │     │
│  │  ┌───────────────────────────────────────────────────────────────┐   │     │
│  │  │  Collection: "past_executions" (few-shot memory)              │   │     │
│  │  │  ──────────────────────────────────────────                    │   │     │
│  │  │  • Previous successful PR generations                          │   │     │
│  │  │  • User request → decomposed tasks mapping                    │   │     │
│  │  │  • Common patterns per team/enterprise                         │   │     │
│  │  └───────────────────────────────────────────────────────────────┘   │     │
│  └─────────────────────────────────────────────────────────────────────┘     │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐     │
│  │              GITHUB (Live Context via MCP/API)                        │     │
│  │                                                                       │     │
│  │  Fetched at runtime (NOT pre-indexed):                                │     │
│  │  • Current file tree of target repos                                  │     │
│  │  • Existing topics/resources (to avoid duplicates)                    │     │
│  │  • Open PRs (to detect conflicts)                                     │     │
│  │  • Branch state                                                        │     │
│  │                                                                       │     │
│  └─────────────────────────────────────────────────────────────────────┘     │
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```
 
### 5.2 When to Use What — Decision Table
 
| Data Type | Storage | Why | Access Pattern |
|---|---|---|---|
| **Conversation history** | PostgreSQL (LangGraph Checkpointer) | Structured, needs exact recall, per-thread | Direct read by thread_id |
| **Session state** (collected fields, grains) | PostgreSQL (LangGraph Checkpointer) | Durable interrupt/resume, exact state | Checkpoint load/save |
| **Pipeline architecture knowledge** | Vector Store (RAG) | Large docs, semantic search needed | Similarity search at intent classification |
| **Repo conventions & examples** | Vector Store (RAG) | Need to find "similar" patterns | Similarity search at plan/render time |
| **Org hierarchy & teams** | Vector Store (RAG) + PostgreSQL | Both structured lookups and fuzzy matching | Hybrid: exact + semantic |
| **Agent configuration** (required fields, templates) | PostgreSQL | Structured, must be exact | Direct query by agent_name |
| **Existing resources in repos** | GitHub API (live) | Must be real-time to avoid conflicts | API call at plan time |
| **Task execution history** | PostgreSQL | Audit trail, structured queries | Query by user/date/status |
| **Few-shot examples** | Vector Store (RAG) | Find most similar past successful execution | Similarity search |
| **User preferences / memory** | LangGraph Store (KV + Vector) | Cross-session, per-user personalization | Namespace lookup |
 
### 5.3 RAG Pipeline Architecture
 
```
┌─────────────────────────────────────────────────────────────┐
│                  RAG INGESTION PIPELINE                       │
│                                                               │
│  Sources:                    Processing:          Store:      │
│                                                               │
│  Architecture docs ──┐                                        │
│  Repo READMEs ───────┤      ┌──────────────┐                │
│  TF module docs ─────┼─────→│ Chunking     │                │
│  Past PRs ───────────┤      │ (semantic    │    ┌────────┐  │
│  Confluence pages ───┤      │  splitter)   │───→│pgvector│  │
│  Team wikis ─────────┘      │              │    │  or    │  │
│                              │ + Metadata   │    │Pinecone│  │
│                              │   tagging    │    └────────┘  │
│                              └──────────────┘                │
│                                                               │
│  Refresh: Weekly batch + webhook on repo push                │
└─────────────────────────────────────────────────────────────┘
```
 
**Where RAG is used in the flow:**
 
1. **Intent Classifier** — Retrieves pipeline architecture context to understand what the user is asking for
2. **Task Decomposer** — Retrieves "what components are needed for X" from architecture docs
3. **Each Domain Agent's `plan` node** — Retrieves repo-specific templates, naming conventions, existing examples
4. **Each Domain Agent's `render` node** — Retrieves similar past generations as few-shot examples
5. **Q&A Agent** — Full RAG pipeline for documentation questions
 
---
 
## 6. Detailed Component Design
 
### 6.1 Intent Classifier (Router)
 
```python
class IntentClassifierNode:
    """
    First node in the super-graph. Uses LLM + RAG context
    to classify user intent into workflow categories.
    """
   
    intents = [
        "pipeline_provisioning",   # "I want to ingest X to Y"
        "documentation_qa",        # "How does the topic naming work?"
        "support_ticket",          # "I'm getting errors in pipeline X"
        "status_check",           # "What's the status of my PR?"
    ]
   
    # RAG retrieval: pulls pipeline architecture context
    # so the classifier understands domain-specific language
   
    # Output: routes to appropriate sub-graph
```
 
### 6.2 Super-Agent (Pipeline Orchestrator)
 
```python
class SuperAgentState(TypedDict):
    messages: list[BaseMessage]
    user_intent: str
    decomposed_tasks: list[Task]        # Ordered by dependency
    common_inputs: dict                  # Shared fields
    agent_results: dict[str, AgentResult]  # Results per agent
    overall_status: str                  # "collecting" | "executing" | "done"
 
class Task(TypedDict):
    task_id: str
    task_type: str                      # "kafka_topic" | "kms_key" | "glue_job" etc.
    agent_name: str                     # Which agent handles this
    depends_on: list[str]              # Task IDs that must complete first
    inputs: dict                        # Specific inputs for this task
    status: str                         # "pending" | "in_progress" | "done" | "failed"
    outputs: dict                       # PR URL, resource ARN, etc.
```
 
### 6.3 Generalized Domain Agent (Template)
 
Every domain agent follows the **same pattern** (your POC generalized):
 
```python
class DomainAgentState(TypedDict):
    """Base state that ALL domain agents share."""
    messages: list[BaseMessage]
    # Common fields (pre-filled by super-agent)
    environment: str
    enterprise: str
    subgroup: str
    source_system: str
    data_classification: str
   
    # Domain-specific fields (each agent extends this)
    domain_fields: dict                # Agent-specific collected fields
    required_fields: list[str]        # What this agent needs
    optional_fields: list[str]        # Nice-to-have
   
    # Execution
    plan: dict                         # Generated plan
    rendered_output: str              # Generated code (TF/YAML/etc)
    pr_url: Optional[str]
    status: str
 
 
def build_domain_agent(agent_config: AgentConfig) -> CompiledGraph:
    """
    Factory that builds any domain agent from configuration.
    All agents share the same graph topology but differ in:
    - required_fields
    - validation_rules
    - templates (for code generation)
    - target_repo
    """
    graph = StateGraph(DomainAgentState)
   
    graph.add_node("normalize", normalize_node)       # Extract fields from conversation
    graph.add_node("collect", collect_node)           # Ask for missing fields
    graph.add_node("validate", validate_node)         # Domain-specific validation
    graph.add_node("plan", plan_node)                 # Generate execution plan
    graph.add_node("render", render_node)             # Generate TF/YAML/code
    graph.add_node("confirm", confirm_node)           # Human approval
    graph.add_node("create_pr", create_pr_node)       # Execute via MCP
   
    # Same routing logic, different configs
    graph.add_edge(START, "normalize")
    graph.add_conditional_edges("normalize", route_after_normalize)
    graph.add_conditional_edges("collect", route_after_collect)
    graph.add_edge("validate", "plan")
    graph.add_edge("plan", "render")
    graph.add_edge("render", "confirm")
    graph.add_conditional_edges("confirm", route_after_confirm)
    graph.add_edge("create_pr", END)
   
    return graph.compile(
        interrupt_before=["normalize", "confirm"],
        checkpointer=postgres_checkpointer
    )
```
 
### 6.4 Agent Configuration (DB-driven)
 
```python
# Stored in PostgreSQL — agents are configured, not coded
AGENT_CONFIGS = {
    "topic_agent": AgentConfig(
        name="topic_agent",
        description="Creates Kafka topics via Terraform PR",
        target_repo="org/confluent-topics",
        required_fields=["source_system", "grain", "pii", "grain_type", "schema_format", "environment"],
        optional_fields=["partitions", "retention_override"],
        output_format="terraform",
        templates=["slt_onetoone_topic_template", "cds_onetoone_topic_template"],
        validation_rules={...},
        rag_collection="repo_knowledge_topics",
    ),
    "kms_agent": AgentConfig(
        name="kms_agent",
        description="Creates KMS encryption keys via Terraform PR",
        target_repo="org/aws-kms-keys",
        required_fields=["key_alias", "environment", "key_usage", "key_spec", "rotation_enabled"],
        optional_fields=["description", "tags"],
        output_format="terraform",
        templates=["kms_key_template"],
        validation_rules={...},
        rag_collection="repo_knowledge_kms",
    ),
    "glue_agent": AgentConfig(
        name="glue_agent",
        description="Creates Glue Jobs/DBs/Tables via Terraform PR",
        target_repo="org/aws-glue-infra",
        required_fields=["database_name", "table_name", "source_format", "target_location", "environment"],
        optional_fields=["partitions", "serde_params"],
        output_format="terraform",
        templates=["glue_db_template", "glue_job_template"],
        validation_rules={...},
        rag_collection="repo_knowledge_glue",
    ),
    # ... more agents
}
```
 
---
 
## 7. Production Infrastructure
 
### 7.1 Deployment Architecture
 
```
┌─────────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster (EKS/AKS)                   │
│                                                                   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌────────────────┐  │
│  │  API Gateway    │  │  LangGraph      │  │  MCP Servers   │  │
│  │  (FastAPI)      │  │  Workers        │  │  (Sidecar)     │  │
│  │                 │  │                 │  │                │  │
│  │  • REST API     │  │  • Graph exec   │  │  • GitHub MCP  │  │
│  │  • WebSocket    │  │  • 3-5 replicas │  │  • TF Validate │  │
│  │  • Auth/SSO     │  │  • Auto-scale   │  │  • AWS MCP     │  │
│  │  • Rate limit   │  │    on queue     │  │                │  │
│  └────────┬────────┘  └───────┬─────────┘  └────────────────┘  │
│           │                    │                                  │
│  ┌────────▼────────────────────▼─────────────────────────────┐  │
│  │                    Message Queue (Redis/SQS)               │  │
│  │            (Decouples API from graph execution)            │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
         │                    │                    │
┌────────▼──────┐  ┌─────────▼────────┐  ┌──────▼───────────┐
│  PostgreSQL   │  │  Redis            │  │  Vector Store    │
│               │  │                   │  │  (pgvector)      │
│  • Checkpoint │  │  • Session cache  │  │                  │
│  • Store      │  │  • Pub/Sub for WS │  │  • RAG indices   │
│  • Audit      │  │  • Rate limiting  │  │  • Embeddings    │
│  • Config     │  │                   │  │                  │
└───────────────┘  └───────────────────┘  └──────────────────┘
```
 
### 7.2 Observability Stack
 
```
LangSmith (Tracing)     →  Every LLM call, every node execution, latency, tokens
OpenTelemetry           →  Distributed tracing across services
Prometheus + Grafana    →  Infra metrics, queue depth, error rates
Structured Logging      →  JSON logs to ELK/CloudWatch
Alerting                →  PagerDuty/Slack on failures, stuck threads, high latency
```
 
---
 
## 8. Migration Path from POC to Production
 
### Phase 1: Foundation (Weeks 1-3)
```
□ Replace InMemorySaver → PostgresSaver
□ Add LangGraph Store for cross-session memory  
□ Externalize agent config to DB (not hardcoded)
□ Add REST API alongside WebSocket
□ Add structured logging + LangSmith tracing
□ Containerize (Docker) + K8s manifests
```
 
### Phase 2: Multi-Agent (Weeks 4-6)
```
□ Refactor current topic agent into DomainAgent template
□ Build Intent Classifier node
□ Build Task Decomposer node  
□ Build Generalized Input Collector
□ Create Super-Agent graph that composes sub-agents
□ Add second domain agent (KMS or Glue) to prove pattern
```
 
### Phase 3: RAG & Context (Weeks 7-8)
```
□ Set up pgvector / vector store
□ Build ingestion pipeline for repo docs + architecture docs
□ Integrate RAG into intent classifier + plan nodes
□ Build GitHub MCP server for live repo context
□ Add few-shot example retrieval from past executions
```
 
### Phase 4: Governance & Production (Weeks 9-12)
```
□ MCP server governance layer (auth, audit, rate limiting)
□ Human-in-the-loop approval workflows
□ SSO integration (Azure AD / Okta)
□ End-to-end testing + chaos testing
□ Production deployment with canary releases
□ Monitoring dashboards + alerting
```
 
---
 
## 9. Key Technical Decisions
 
| Decision | Choice | Rationale |
|---|---|---|
| Orchestration Framework | **LangGraph (self-hosted)** | Best multi-agent composition, interrupt/resume, subgraph support |
| LLM | **Azure OpenAI GPT-4.1** | Enterprise compliance, existing relationship |
| Checkpointing | **PostgresSaver** | Durable, scalable, queryable |
| Memory | **LangGraph Store (Postgres-backed)** | Built-in vector + KV, per-user namespaces |
| Vector Store | **pgvector (in same Postgres)** | Simplifies infra, good enough for <1M docs |
| Tool Execution | **MCP Servers** | Vendor-neutral, governed, auditable |
| API | **FastAPI (REST + WebSocket)** | Already proven in POC, streaming support |
| Queue | **Redis Streams** | Decouple API from graph workers, pub/sub for WS |
| Deployment | **Kubernetes (EKS/AKS)** | Enterprise-grade scaling, existing K8s skills |
| Auth | **Azure AD SSO + JWT** | Enterprise standard |
| Observability | **LangSmith + OpenTelemetry** | Full LLM tracing + distributed tracing |
 
---
 
## 10. Why NOT AgentCore for This Use Case
 
| Factor | AgentCore | Self-hosted LangGraph |
|---|---|---|
| Multi-agent composition | Limited (single agent focus) | Native subgraphs |
| Custom orchestration logic | Constrained | Full control |
| Interrupt/resume patterns | Basic | Advanced (multi-point) |
| Azure OpenAI support | AWS Bedrock focused | Any LLM provider |
| MCP integration | Not native | Community + custom MCP |
| Existing POC migration | Complete rewrite | Evolutionary upgrade |
| Vendor lock-in | High (AWS) | Low |
 
**Verdict:** Use LangGraph self-hosted. AgentCore is better suited for simpler, single-agent AWS-native use cases. Your multi-agent, multi-repo, multi-provider architecture needs the flexibility of LangGraph.
 
---
 
## 11. Example: End-to-End Flow
 
```
User: "I want to ingest ERP vendor data with PII to the raw lakehouse layer"
 
1. AI Gateway → validates JWT, logs request, passes to graph
 
2. Intent Classifier:
   - RAG retrieves: pipeline architecture docs
   - LLM classifies: "pipeline_provisioning"
   - Routes to: Super-Agent
 
3. Super-Agent → Task Decomposer:
   - RAG retrieves: "what's needed for ERP→Raw with PII?"
   - Decomposes into:
     a. KMS Key (for PII encryption)        → kms_agent
     b. Kafka Topic (ingestion channel)      → topic_agent  
     c. S3 Bucket (raw storage)              → s3_agent
     d. Glue Database (catalog)              → glue_agent
     e. Glue Job (ETL from Kafka to S3)      → pipeline_agent
   - Dependency order: a → b → c,d → e
 
4. Generalized Input Collector:
   Bot: "Which environment — dev or prod?"
   User: "dev"
   Bot: "Which enterprise/business unit?"
   User: "finance"
   Bot: "What's the source system name in our catalog?"
   User: "sap_erp"
   → Stores: {env: "dev", enterprise: "finance", source_system: "sap_erp", pii: true}
 
5. Domain Agent Execution (sequential by dependency):
   
   a. KMS Agent:
      - Pre-filled: env=dev, enterprise=finance, pii=true
      - Collects: key_alias (auto-suggests: "finance-sap-erp-pii-dev")
      - Renders: kms.tf
      - Creates PR → org/aws-kms-keys#142
   
   b. Topic Agent (YOUR EXISTING POC):
      - Pre-filled: env=dev, source_system=sap_erp, pii=true
      - Collects: grain="vendor", grain_type="slt_1to1", schema="avro"
      - Renders: topics_sap_erp.tf
      - Creates PR → org/confluent-topics#89
   
   c. S3 + Glue Agents (parallel):
      - Similar flow...
   
   d. Pipeline Agent (after c):
      - Creates Glue job referencing topic + S3 + KMS
      - Creates PR → org/glue-jobs#45
 
6. Summary:
   Bot: "I've created 5 PRs for your ERP vendor ingestion pipeline:
         • KMS Key: PR #142 (pending approval)
         • Kafka Topic: PR #89 (pending approval)  
         • S3 Bucket: PR #201 (pending approval)
         • Glue DB: PR #156 (pending approval)
         • Glue Job: PR #45 (pending approval)
         
         Once approved, your pipeline will be provisioned automatically."
```
 
---
 
## 12. Summary Table: RAG vs DB vs Live API
 
| What | Where | Why |
|---|---|---|
| "What components do I need for X?" | **RAG** (pipeline_architecture collection) | Semantic understanding of org's data platform |
| "What's the naming convention for topics?" | **RAG** (repo_knowledge collection) | Pattern matching from examples |
| "Show me similar past requests" | **RAG** (past_executions collection) | Few-shot retrieval |
| "What fields has the user provided?" | **DB** (PostgreSQL checkpointer) | Exact state, durable |
| "What's the conversation so far?" | **DB** (PostgreSQL checkpointer) | Ordered messages, per-thread |
| "Does this topic already exist?" | **Live API** (GitHub MCP) | Must be real-time |
| "What agents are available?" | **DB** (agent_config table) | Structured registry |
| "What did this user do last time?" | **DB** (LangGraph Store, per-user namespace) | Cross-session memory |
| "What are the org's compliance rules?" | **RAG** (organizational_context) | Policy docs, semantic |
| "Is there a conflicting open PR?" | **Live API** (GitHub MCP) | Must be real-time |
 
---
 
This architecture gives you: **governed multi-agent orchestration** with clear separation of reasoning (LangGraph), context (RAG + DB), and execution (MCP servers) — exactly matching the enterprise platform vision in your diagram.
 
 
 