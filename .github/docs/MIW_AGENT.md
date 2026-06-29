# MIW Agent — Graph Design

## What MIW Does

MIW is the repo for AWS resource provisioning. Users provide requirements in YAML files,
create/update a PR, and on approval the AWS resource is provisioned.

Our agent automates: collecting requirements → generating YAML → creating the PR.

---

## Resource Types (6)

| Resource | Description |
|----------|-------------|
| `s3` | S3 bucket provisioning |
| `glue_db` | Glue database/table creation |
| `iam` | IAM role/policy creation |
| `resource_policy` | Resource-based policies |
| `smus_project` | SMUS project setup |
| `smus_role` | SMUS role assignment |

---

## MIW Agent Graph Topology

```
START
  │
  ▼
┌──────────────────┐
│ UNDERSTAND       │  Parse user request
│                  │  Determine resource_type(s) needed
│                  │  Determine if single or multi-resource
│                  │  Output: resource_types[], understanding
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ COLLECT COMMON   │  ← Uses: Collector Skill + common_collection.md
│                  │  Gets: environment, enterprise, subgroup, etc.
│                  │  Multi-turn: loops until all common fields gathered
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ PLAN             │  Present task plan to user
│                  │  "I'll create: S3 bucket + Glue DB + IAM role. OK?"
│                  │  User confirms or modifies the plan
└────────┬─────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────────┐
│ TASK LOOP (for each resource in plan, respecting dependencies)   │
│                                                                   │
│  ┌──────────────────┐                                            │
│  │ COLLECT RESOURCE │  ← Uses: Collector Skill + {resource}/collection.md │
│  │                  │  Gets resource-specific fields              │
│  │                  │  May auto-derive from common fields         │
│  └────────┬─────────┘                                            │
│           │                                                       │
│           ▼                                                       │
│  ┌──────────────────┐                                            │
│  │ GENERATE         │  ← Uses: Generator Skill + {resource}/generation.md │
│  │                  │  Reads template, uses RAG for examples      │
│  │                  │  Output: YAML content + file path           │
│  └────────┬─────────┘                                            │
│           │                                                       │
│           ▼                                                       │
│  ┌──────────────────┐                                            │
│  │ VALIDATE         │  ← Uses: Validator Skill + {resource}/validation.md │
│  │                  │  YAML syntax check                          │
│  │                  │  Naming rules, policy checks                │
│  │                  │  Duplicate check via GitHub MCP             │
│  └────────┬─────────┘                                            │
│           │                                                       │
│      ┌────┴────┐                                                  │
│      │ Valid?  │                                                  │
│      └──┬───┬──┘                                                  │
│    NO   │   │ YES                                                 │
│    ▼    │   ▼                                                     │
│  (back to   │                                                     │
│  GENERATE   │                                                     │
│  max 2x)    │                                                     │
│             ▼                                                     │
│  ┌──────────────────┐                                            │
│  │ CONFIRM          │  ← Uses: Confirm Skill                    │
│  │                  │  INTERRUPT: show code + explanation         │
│  │                  │  Wait for user approval                     │
│  └────────┬─────────┘                                            │
│           │ (approved)                                            │
│           ▼                                                       │
│  ┌──────────────────┐                                            │
│  │ CREATE PR        │  ← Uses: PR Creator Skill                 │
│  │                  │  Branch, commit YAML, open PR               │
│  └────────┬─────────┘                                            │
│           │                                                       │
│      ┌────┴──────────┐                                           │
│      │ More tasks?   │── YES → next resource → COLLECT RESOURCE  │
│      └────┬──────────┘                                           │
│      NO   │                                                       │
└───────────┼───────────────────────────────────────────────────────┘
            │
            ▼
┌──────────────────┐
│ SUMMARIZE        │  Present all PRs created + next steps
└────────┬─────────┘
         │
         ▼
       END
```

---

## State Schema (MIW Agent)

```python
class MIWState(TypedDict):
    # Conversation
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    thread_id: str

    # Understanding
    raw_request: str                     # Original user message
    resource_types: list[str]            # ["s3", "glue_db", "iam"]
    understanding: str                   # Structured interpretation

    # Common fields (collected once, shared across tasks)
    common_fields: dict                  # {env, enterprise, subgroup, ...}
    common_collection_complete: bool

    # Plan
    task_plan: list[dict]                # [{resource_type, depends_on, status}]
    plan_approved: bool

    # Current task context
    current_task_index: int
    current_resource_type: str
    current_collection_schema: str       # MD content loaded for this resource
    current_generation_template: str     # MD content loaded for this resource
    current_validation_rules: str        # MD content loaded for this resource

    # Collector output (per task)
    collected_fields: dict
    resource_collection_complete: bool

    # Generator output (per task)
    generated_code: str
    generated_file_path: str
    generation_explanation: str

    # Validator output (per task)
    validation_passed: bool
    validation_errors: list[str]
    validation_warnings: list[str]
    retry_count: int

    # PR output (per task)
    pr_url: str
    branch_name: str

    # Overall tracking
    completed_tasks: list[dict]          # [{resource_type, pr_url, status}]
    overall_status: str                  # routing|collecting|generating|validating|confirming|done
    error: str | None
```

---

## Nodes — What Each Does

| Node | Responsibility (SRP) | Calls Skill? | Calls Tool? |
|------|----------------------|:------------:|:-----------:|
| `understand` | Parse intent, determine resources needed | No | RAG (optional) |
| `collect_common` | Gather shared fields (env, enterprise, etc.) | Collector Skill | No |
| `plan` | Build ordered task list, present to user | No | No |
| `collect_resource` | Gather resource-specific fields | Collector Skill | No |
| `generate` | Produce YAML code | Generator Skill | GitHub MCP (read repo), RAG |
| `validate` | Check generated code | Validator Skill | GitHub MCP (duplicate check) |
| `confirm` | Human approval gate | Confirm Skill | No |
| `create_pr` | Push code, open PR | PR Creator Skill | GitHub MCP (write) |
| `summarize` | Final summary to user | No | No |

---

## Routing Logic

| From | Condition | To |
|------|-----------|-----|
| `understand` | always | `collect_common` |
| `collect_common` | `common_collection_complete = false` | `__end__` (wait for user input) |
| `collect_common` | `common_collection_complete = true` | `plan` |
| `plan` | `plan_approved = false` | `__end__` (wait for approval) |
| `plan` | `plan_approved = true` | `collect_resource` |
| `collect_resource` | `resource_collection_complete = false` | `__end__` (wait for user) |
| `collect_resource` | `resource_collection_complete = true` | `generate` |
| `generate` | always | `validate` |
| `validate` | `validation_passed = false` AND `retry_count < 2` | `generate` |
| `validate` | `validation_passed = false` AND `retry_count >= 2` | `__end__` (escalate) |
| `validate` | `validation_passed = true` | `confirm` |
| `confirm` | INTERRUPT (wait for human) | `create_pr` |
| `create_pr` | more tasks remaining | `collect_resource` (next task) |
| `create_pr` | no more tasks | `summarize` |
| `summarize` | always | `__end__` |

---

## Dependency Handling Between Resources

Some resources depend on others. Example:
- Glue DB may need S3 bucket ARN
- IAM role may reference the Glue DB

The `plan` node determines execution order. `completed_tasks` in state carries
outputs (ARNs, names) from prior tasks so downstream tasks can reference them.

```
Example dependency chain:
  s3 → glue_db (needs s3 bucket path) → iam (needs glue_db ARN)
```

The task loop processes in dependency order. Each completed task's output
feeds into the next task's `collect_resource` context.
