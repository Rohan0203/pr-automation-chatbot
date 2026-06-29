# Shared Skills & Tools

## Design Principle

Skills are **reusable node functions** that any repo agent can invoke.
They don't know about MIW, MIF, or any specific repo — they operate purely on
the context (md files, fields) passed to them via state.

---

## Skills

### 1. Collector Skill

**Single Responsibility:** Gather required fields from the user via conversation.

```
Input:
  - schema_md: str        → The collection.md content (defines required/optional fields)
  - messages: list        → Conversation history
  - already_collected: dict → Fields already known (from common or prior tasks)

Output:
  - collected_fields: dict  → Extracted field values
  - complete: bool          → All required fields gathered?
  - follow_up_message: str  → Question to ask user (if incomplete)
```

**Behavior:**
- Parses the schema.md to understand what fields are needed
- Scans conversation history to extract already-provided values
- Merges with `already_collected` to avoid re-asking
- If fields missing → generates a natural follow-up question
- If all required fields gathered → returns complete=True
- Smart defaults: suggests sensible defaults from schema, asks user to confirm

**Key Design:**
- The LLM does the parsing and question generation
- The schema.md is the "prompt" that tells the LLM what to collect
- No hardcoded field logic — fully driven by the md content

---

### 2. Generator Skill

**Single Responsibility:** Generate infrastructure code from collected fields + template.

```
Input:
  - template_md: str       → The generation.md content (patterns, structure, conventions)
  - collected_fields: dict → All field values for this resource
  - repo_context: str      → Current repo file tree / existing examples (from RAG/GitHub)
  - past_examples: list    → Similar past generations (from RAG)

Output:
  - code: str              → Generated infrastructure code (YAML, HCL, JSON — template decides)
  - file_path: str         → Where this file goes in the repo
  - explanation: str       → Human-readable explanation of what was generated
```

**Behavior:**
- Reads template.md for file format, structure, naming conventions
- Uses RAG examples as few-shot context
- Uses repo_context to match existing style
- LLM generates the actual code
- Returns the code + target file path + explanation

**Key Design:**
- Format-agnostic: template.md defines whether output is YAML, HCL, or JSON
- Never hardcodes file structure — template drives everything
- Uses existing repo examples for style consistency

---

### 3. Validator Skill

**Single Responsibility:** Validate generated code against rules. Does NOT fix.

```
Input:
  - code: str              → Generated code to validate
  - rules_md: str          → The validation.md content (rules checklist)
  - file_format: str       → "yaml" | "hcl" | "json" (for syntax check)

Output:
  - passed: bool           → All checks passed?
  - errors: list[str]      → Blocking issues (must fix)
  - warnings: list[str]    → Non-blocking issues (informational)
```

**Behavior:**
- Syntax validation (parse YAML/HCL/JSON)
- Rule evaluation: reads validation.md, checks each rule against the code
- Naming pattern checks (regex-based)
- Security/policy checks
- Returns structured pass/fail with specific error messages

**Key Design:**
- Does NOT attempt to fix errors — that's the Generator's job on retry
- Clear error messages that the Generator can understand on next attempt
- Rules are entirely in .md files — no hardcoded validation logic

---

### 4. PR Creator Skill

**Single Responsibility:** Create a branch, commit code, open a PR.

```
Input:
  - code: str              → File content to commit
  - file_path: str         → Path in repo
  - pr_config: dict        → {repo_url, branch_prefix, pr_template, reviewers, base_branch}
  - title: str             → PR title
  - description: str       → PR body (from generation explanation)

Output:
  - pr_url: str            → URL of created PR
  - branch_name: str       → Branch name used
  - status: str            → "created" | "failed"
  - error: str | None      → Error message if failed
```

**Behavior:**
- Generate branch name: `{branch_prefix}/{resource_type}-{timestamp}`
- Create branch from base (usually `main`)
- Commit the generated file
- Open PR with description + assign reviewers
- Return PR URL

**Tools Used:** GitHub MCP (create_branch, commit_file, create_pr)

---

### 5. Confirm Skill (Human-in-the-Loop)

**Single Responsibility:** Present generated output to user and collect approval.

```
Input:
  - code: str              → Generated code to show
  - explanation: str       → What was generated and why
  - warnings: list[str]    → Any non-blocking validation warnings
  - file_path: str         → Where it will go

Output:
  - decision: str          → "approved" | "rejected" | "modify"
  - modifications: str     → User's modification request (if "modify")
```

**Behavior:**
- Formats a clear summary: what will be created, where, with what config
- Shows the actual generated code
- Shows any warnings
- Uses LangGraph INTERRUPT — pauses graph execution
- Resumes when user responds

---

## Tools (MCP Integrations)

### GitHub MCP

| Operation | Used By | Purpose |
|-----------|---------|---------|
| `read_file_tree` | Generator | Understand repo structure |
| `read_file` | Generator | Read existing examples |
| `search_files` | Validator | Check for duplicates |
| `list_prs` | Validator | Check for conflicting open PRs |
| `create_branch` | PR Creator | Create feature branch |
| `commit_files` | PR Creator | Push generated code |
| `create_pr` | PR Creator | Open pull request |
| `add_reviewers` | PR Creator | Assign reviewers |

### RAG Search

| Operation | Used By | Purpose |
|-----------|---------|---------|
| `search_examples` | Generator | Find similar past generations |
| `search_docs` | Understand node | Retrieve architecture knowledge |
| `search_conventions` | Generator | Repo-specific conventions |

### Terraform Validate (Future — MIF Agent)

| Operation | Used By | Purpose |
|-----------|---------|---------|
| `validate_hcl` | Validator | Syntax check Terraform |
| `plan_dry_run` | MIF-specific node | Preview changes |

---

## Skill Invocation Pattern

Each skill is a Python function that a graph node calls:

```python
# In miw_agent/nodes.py

from skills.collector import collect_fields
from skills.generator import generate_code
from skills.validator import validate_code
from skills.pr_creator import create_pull_request

async def collect_resource_node(state: MIWState) -> dict:
    """MIW graph node that uses the Collector Skill."""
    
    # Load the right schema for current resource
    schema_md = load_config(f"resources/{state['current_resource_type']}/collection.md")
    
    # Invoke the shared skill
    result = await collect_fields(
        schema_md=schema_md,
        messages=state["messages"],
        already_collected=state["common_fields"],  # Pass common fields in
    )
    
    return {
        "collected_fields": result["collected_fields"],
        "resource_collection_complete": result["complete"],
        "messages": [result["follow_up_message"]] if not result["complete"] else [],
    }
```

This pattern means:
- The **node** (in the agent) knows WHICH config to load
- The **skill** (shared) does the actual work, config-driven
- Easy to test skills in isolation with mock configs
