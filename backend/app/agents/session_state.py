"""
Session & Agent State — In-memory state management for the generator agent.

AgentState: tracks a single resource being built (fields, phase, YAML, PR state).
SessionState: tracks a full user session (current agent, completed resources, history).
StructuredFlow: tracks the guided Q1→Q2→Q3→Collection→Confirmation flow.
_sessions: global in-memory session store, keyed by session_id.
"""
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# RESOURCE TYPE DEFINITIONS — structured flow options
# ═══════════════════════════════════════════════════════════════

RESOURCE_OPTIONS = {
    "s3_source": {
        "label": "Source Bucket",
        "description": "Data ingestion from source systems",
        "category": "S3",
        "resource_type": "s3",
        "auto_fields": {"usage_type": "Source"},
        "account_type": "lakehouse",  # Always Lakehouse
        "needs_account_ask": False,
    },
    "s3_dataproduct": {
        "label": "DataProduct Bucket",
        "description": "Transformed / processed data",
        "category": "S3",
        "resource_type": "s3",
        "auto_fields": {"usage_type": "DataProduct"},
        "account_type": "compute",  # Always Compute
        "needs_account_ask": False,
    },
    "s3_scripts": {
        "label": "Scripts Bucket",
        "description": "ETL scripts and code",
        "category": "S3",
        "resource_type": "s3",
        "auto_fields": {"usage_type": "Scripts"},
        "account_type": None,  # User must choose
        "needs_account_ask": True,
    },
    "s3_engassets": {
        "label": "EngAssets Bucket",
        "description": "Engineering assets",
        "category": "S3",
        "resource_type": "s3",
        "auto_fields": {"usage_type": "EngAssets"},
        "account_type": None,  # User must choose
        "needs_account_ask": True,
    },
    "glue_raw": {
        "label": "Raw Source DB",
        "description": "Raw data ingestion layer",
        "category": "Glue DB",
        "resource_type": "glue_db",
        "auto_fields": {"data_construct": "Source", "data_layer": "raw"},
        "account_type": "lakehouse",  # Always Lakehouse
        "needs_account_ask": False,
        "needs_cdp_ask": True,
    },
    "glue_curated": {
        "label": "Curated DB",
        "description": "Processed / curated data layer",
        "category": "Glue DB",
        "resource_type": "glue_db",
        "auto_fields": {"data_construct": "DataProduct", "data_layer": "curated"},
        "account_type": "compute",  # Always Compute
        "needs_account_ask": False,
    },
    "glue_serving": {
        "label": "Serving DB",
        "description": "Analytics / serving layer",
        "category": "Glue DB",
        "resource_type": "glue_db",
        "auto_fields": {"data_construct": "DataProduct", "data_layer": "serving"},
        "account_type": "compute",  # Always Compute
        "needs_account_ask": False,
        "needs_purpose_ask": True,
    },
    "glue_internal": {
        "label": "Internal DB",
        "description": "Internal processing / staging",
        "category": "Glue DB",
        "resource_type": "glue_db",
        "auto_fields": {"data_layer": "internal"},
        "account_type": None,  # Both allowed — ask
        "needs_account_ask": True,
        "needs_construct_ask": True,
    },
}

# Enterprise → subgroup map (for Q3 filtering)
ENTERPRISE_SUBGROUPS = {
    "AGTR": ["EMEA", "NA", "LATAM", "APAC", "WTG", "WTG_CDAS", "OT", "CRM", "TCM", "MET"],
    "CORP": ["GI_SUST", "EHS", "FIN", "GTC", "CPT", "HR", "AUDIT", "DTD", "LAW", "DTD_DPE", "RMG", "FSQR", "DTD_GIS"],
    "FOOD": ["FSGL", "FS_NA", "FS_LATAM", "FS_APAC", "FS_EMEA", "PRGL", "PR_LATAM", "PR_NA", "PR_APAC", "SALT", "CE", "RD"],
    "SPEC": ["ANH", "CBI", "DS"],
}


# ═══════════════════════════════════════════════════════════════
# STRUCTURED FLOW — guided Q1→Q2→Q3→Collection→Confirmation
# ═══════════════════════════════════════════════════════════════

class StructuredFlow:
    """Tracks the guided conversation flow state."""

    def __init__(self):
        self.phase: str = "q1_env"
        # q1_env → q2_resource → q2_enterprise → q3_conditionals → text_collection → confirmation

        # Q1
        self.environment: Optional[str] = None  # "dev" or "prd"

        # Q2 — supports multi-resource selection
        self.selected_resource: Optional[str] = None  # key from RESOURCE_OPTIONS (current resource)
        self.selected_resources: list[str] = []  # ALL selected resource keys
        self.current_resource_index: int = 0  # which resource we're currently processing
        self.selected_enterprise: Optional[str] = None  # "AGTR", "FOOD", etc.

        # Q3 conditional answers — SHARED across all resources
        self.account_placement: Optional[str] = None  # "lakehouse" or "compute"
        self.cdp_flag: Optional[str] = None  # "yes" or "no"
        self.serving_purpose: Optional[str] = None  # free-form
        self.data_construct: Optional[str] = None  # for internal: "Source" or "DataProduct"
        self.subgroup: Optional[str] = None  # enterprise subgroup

        # Per-resource Q3 answers (for questions that differ per resource)
        self.per_resource_q3: dict[str, dict] = {}
        # e.g. {"glue_raw": {"cdp_flag": "no"}, "s3_scripts": {"account_placement": "lakehouse"}}

        # Batched Q3 question queue (unique questions across ALL resources)
        self.pending_q3: list[str] = []
        self.current_q3_index: int = 0
        # Track which resource a Q3 question belongs to (for context in prompts)
        self.q3_resource_context: dict[str, str] = {}  # {"cdp_flag": "glue_raw", ...}

        # Global classification/privacy — asked once for all Glue DBs
        self.data_classification: Optional[str] = None
        self.data_privacy: Optional[str] = None

        # Multi-resource tracking — completed resource YAMLs/fields
        self.completed_resource_yamls: list[dict] = []  # [{resource_type, fields, yaml, resource_key}]

    def get_resource_config(self) -> dict:
        """Return the RESOURCE_OPTIONS entry for the selected resource."""
        if self.selected_resource and self.selected_resource in RESOURCE_OPTIONS:
            return RESOURCE_OPTIONS[self.selected_resource]
        return {}

    def build_auto_fields(self) -> dict:
        """Build the auto-populated fields from structured flow answers."""
        config = self.get_resource_config()
        if not config:
            return {}

        fields = dict(config.get("auto_fields", {}))

        # Environment → data_env (Glue) or environment (S3)
        if self.environment:
            if config["resource_type"] == "s3":
                fields["environment"] = self.environment
            else:
                fields["data_env"] = self.environment

        # Enterprise
        if self.selected_enterprise:
            fields["enterprise_or_func_name"] = self.selected_enterprise

        # Subgroup
        if self.subgroup is not None:
            fields["enterprise_or_func_subgrp_name"] = self.subgroup

        # CDP flag (Glue raw)
        if self.cdp_flag is not None:
            fields["cdp_flag"] = self.cdp_flag

        # Serving purpose
        if self.serving_purpose:
            fields["purpose"] = self.serving_purpose

        # Internal construct
        if self.data_construct:
            fields["data_construct"] = self.data_construct

        return fields

    def compute_q3_questions(self) -> list[str]:
        """Compute UNIQUE Q3 questions across ALL selected resources.
        Subgroup is always asked first. Per-resource questions follow."""
        questions = []
        self.q3_resource_context = {}

        # Subgroup — always ask once (shared across all resources)
        questions.append("subgroup")

        # Collect unique conditional questions across all selected resources
        for res_key in self.selected_resources:
            config = RESOURCE_OPTIONS.get(res_key, {})

            if config.get("needs_account_ask") and "account_placement" not in questions:
                questions.append("account_placement")
                self.q3_resource_context["account_placement"] = res_key

            if config.get("needs_construct_ask") and "data_construct" not in questions:
                questions.append("data_construct")
                self.q3_resource_context["data_construct"] = res_key

            if config.get("needs_cdp_ask") and "cdp_flag" not in questions:
                questions.append("cdp_flag")
                self.q3_resource_context["cdp_flag"] = res_key

            if config.get("needs_purpose_ask") and "serving_purpose" not in questions:
                questions.append("serving_purpose")
                self.q3_resource_context["serving_purpose"] = res_key

        self.pending_q3 = questions
        self.current_q3_index = 0
        return questions

    def has_glue_resources(self) -> bool:
        """Check if any selected resource is a Glue DB."""
        return any(
            RESOURCE_OPTIONS.get(k, {}).get("resource_type") == "glue_db"
            for k in self.selected_resources
        )

    def build_auto_fields_for(self, resource_key: str) -> dict:
        """Build auto-populated fields for a specific resource key."""
        config = RESOURCE_OPTIONS.get(resource_key, {})
        if not config:
            return {}

        fields = dict(config.get("auto_fields", {}))

        # Environment
        if self.environment:
            if config["resource_type"] == "s3":
                fields["environment"] = self.environment
            else:
                fields["data_env"] = self.environment

        # Enterprise
        if self.selected_enterprise:
            fields["enterprise_or_func_name"] = self.selected_enterprise

        # Subgroup
        if self.subgroup is not None:
            fields["enterprise_or_func_subgrp_name"] = self.subgroup

        # Per-resource Q3 answers
        per_res = self.per_resource_q3.get(resource_key, {})

        # CDP flag — applies to raw source
        cdp = per_res.get("cdp_flag") or self.cdp_flag
        if cdp is not None:
            fields["cdp_flag"] = cdp

        # Serving purpose — applies to serving DB
        purpose = per_res.get("serving_purpose") or self.serving_purpose
        if purpose:
            fields["purpose"] = purpose

        # Account placement
        acct = per_res.get("account_placement") or self.account_placement
        if acct:
            fields["account_placement"] = acct

        # Internal construct
        construct = per_res.get("data_construct") or self.data_construct
        if construct:
            fields["data_construct"] = construct

        # Global classification / privacy for Glue
        if config["resource_type"] == "glue_db":
            if self.data_classification:
                fields["data_classification"] = self.data_classification
            if self.data_privacy:
                fields["data_privacy"] = self.data_privacy

        return fields

    def current_q3_question(self) -> Optional[str]:
        """Get the current Q3 question to ask."""
        if self.current_q3_index < len(self.pending_q3):
            return self.pending_q3[self.current_q3_index]
        return None

    def advance_q3(self):
        """Move to the next Q3 question."""
        self.current_q3_index += 1

    def advance_to_next_resource(self) -> bool:
        """Switch to the next resource in the multi-resource list.
        Returns True if there is a next resource, False if all done."""
        self.current_resource_index += 1
        if self.current_resource_index < len(self.selected_resources):
            self.selected_resource = self.selected_resources[self.current_resource_index]
            return True
        return False

    def has_more_resources(self) -> bool:
        """Check if there are more resources to process."""
        return self.current_resource_index < len(self.selected_resources) - 1

    def current_resource_label(self) -> str:
        """Human-readable label for the current resource."""
        config = self.get_resource_config()
        return config.get("label", self.selected_resource or "resource")

    def resource_progress(self) -> str:
        """E.g. '1/3' — current resource number out of total."""
        return f"{self.current_resource_index + 1}/{len(self.selected_resources)}"


# ═══════════════════════════════════════════════════════════════
# STATE CLASSES
# ═══════════════════════════════════════════════════════════════

class AgentState:
    """In-memory state for a single resource being built."""

    def __init__(self):
        self.resource_type: Optional[str] = None
        self.collected_fields: dict = {}
        self.current_field: Optional[str] = None
        self.phase: str = "idle"  # idle, detecting, collecting, awaiting_confirmation, reviewing, review_failed, batch_prompt, pr_setup, done
        self.generated_yaml: Optional[str] = None
        self.field_retries: dict = {}  # {field_name: retry_count}
        # Collection flow flags
        self.initial_listing_shown: bool = False   # Has the upfront field listing been shown?
        self.optional_fields_offered: bool = False  # Has the optional fields phase been presented?
        # Review state (populated during reviewing phase)
        self.review_result = None  # ReviewResult from reviewer_agent
        self.review_attempts: int = 0  # Track review cycles to detect loops
        # PR setup state (populated during pr_setup phase)
        self.pr_branch_name: Optional[str] = None
        self.pr_title: Optional[str] = None
        self.pr_body: Optional[str] = None
        self.pr_target_branch: Optional[str] = None
        self.available_branches: list[str] = []
        self.fork_exists: Optional[bool] = None
        self.fork_full_name: Optional[str] = None
        self.pr_sub_phase: str = "ask_branch"  # ask_branch, ask_title, show_files, confirm


class SessionState:
    """Manages the full session state including multiple resources."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.current_agent: Optional[AgentState] = None
        self.completed_resources: list[dict] = []
        self.conversation_history: list[dict] = []
        self.conversation_summary: Optional[str] = None  # Loaded from DB on resume
        self.github_token: Optional[str] = None
        self.github_username: Optional[str] = None
        self.paused_pr_state: Optional[dict] = None  # Saved PR sub-phase state when user interrupts to add a resource
        self.batch: list[dict] = []  # Resources ready for PR submission
        self.structured_flow: Optional[StructuredFlow] = None  # Guided Q1→Q2→Q3 flow

    def start_new_resource(self) -> AgentState:
        self.current_agent = AgentState()
        return self.current_agent

    def complete_current_resource(self):
        if self.current_agent and self.current_agent.generated_yaml:
            self.completed_resources.append({
                "resource_type": self.current_agent.resource_type,
                "yaml": self.current_agent.generated_yaml,
                "fields": self.current_agent.collected_fields,
                "pr_url": getattr(self.current_agent, "_pr_url", None),
            })
        self.current_agent = None

    # ─── BATCH METHODS ─────────────────────────────────────────

    def add_to_batch(self, agent: AgentState) -> dict:
        """Serialize current agent into a batch entry. Returns the entry."""
        fields = agent.collected_fields or {}
        resource_name = (
            fields.get("bucket_name")
            or fields.get("database_name")
            or fields.get("role_name")
            or "unknown"
        )
        entry = {
            "resource_type": agent.resource_type,
            "intake_id": fields.get("intake_id", "unknown"),
            "resource_name": resource_name,
            "fields": fields.copy(),
            "yaml": agent.generated_yaml,
            "review_result": agent.review_result.to_dict() if agent.review_result else None,
        }
        self.batch.append(entry)
        return entry

    def remove_from_batch(self, index: int) -> dict | None:
        """Remove batch entry by 1-based index. Returns removed entry or None."""
        if 1 <= index <= len(self.batch):
            return self.batch.pop(index - 1)
        return None

    def get_batch_summary(self) -> str:
        """Return a formatted markdown table of the batch."""
        if not self.batch:
            return "No resources in your batch."
        count = len(self.batch)
        lines = [
            f"📦 **Batch Summary** ({count} resource{'s' if count != 1 else ''}):\n",
            "| # | Type | Name | Intake ID | Status |",
            "|---|------|------|-----------|--------|",
        ]
        for i, entry in enumerate(self.batch, 1):
            rtype = entry["resource_type"].upper()
            name = entry["resource_name"]
            iid = entry["intake_id"]
            lines.append(f"| {i} | {rtype} | `{name}` | {iid} | ✅ Ready |")
        return "\n".join(lines)

    def edit_batch_resource(self, index: int) -> AgentState | None:
        """Pull resource at 1-based index back into current_agent for editing.
           Removes it from batch. Returns the new AgentState or None."""
        if index < 1 or index > len(self.batch):
            return None
        entry = self.batch.pop(index - 1)
        agent = self.start_new_resource()
        agent.resource_type = entry["resource_type"]
        agent.collected_fields = entry["fields"].copy()
        agent.generated_yaml = entry["yaml"]
        agent.phase = "awaiting_confirmation"
        agent.initial_listing_shown = True
        agent.optional_fields_offered = True
        return agent

    def clear_batch(self):
        """Clear the batch after PR creation."""
        self.batch.clear()


# ═══════════════════════════════════════════════════════════════
# SESSION STORE
# ═══════════════════════════════════════════════════════════════

_sessions: dict[str, SessionState] = {}


def get_session(session_id: str) -> SessionState:
    """Get or create an in-memory session for the given ID."""
    if session_id not in _sessions:
        _sessions[session_id] = SessionState(session_id)
    return _sessions[session_id]


def delete_session(session_id: str):
    """Remove a session from the in-memory store."""
    _sessions.pop(session_id, None)


# ═══════════════════════════════════════════════════════════════
# BRANCH NAME HELPERS
# ═══════════════════════════════════════════════════════════════

def is_valid_branch_name(name: str) -> bool:
    """Check if a string looks like a valid git branch name (not just a plain word)."""
    if not name or len(name) < 2:
        return False
    # Must not contain characters invalid in git refs
    has_invalid = bool(re.search(r'[~^: \\@{}\[\]]', name))
    if has_invalid:
        return False
    # Must contain at least one separator char (/, -, _) to look like a branch name
    has_separator = bool(re.search(r'[/_-]', name))
    return has_separator


def extract_branch_name(user_message: str) -> Optional[str]:
    """
    Extract a branch name from a natural-language message.
    Handles patterns like:
      - "Branch name should be rohan-feature-a-s3"
      - "change branch to feature_a_s3"
      - "set branch as feature/my-config"
      - "use branch feature_a_s3"
      - "branch: feature_a_s3"
      - Just a branch-like string: "feature_a_s3"
    """
    text = user_message.strip()
    text_lower = text.lower()

    # Pattern 1: explicit phrasing like "change branch to X"
    patterns = [
        r'(?:change|set|rename|update)\s+(?:the\s+)?branch\s*(?:name)?\s+(?:to|as)\s+(.+)',
        r'branch\s*(?:name)?\s+(?:should\s+be|is|will\s+be|=)\s+(.+)',
        r'(?:use|try)\s+(?:the\s+)?branch\s*(?:name)?\s+(.+)',
        r'branch\s*(?:name)?\s*[:=]\s*(.+)',
        r'(?:name|call)\s+(?:it|the\s+branch)\s+(.+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            candidate = text[match.start(1):match.end(1)].strip().strip("'\"` ")
            if candidate and is_valid_branch_name(candidate):
                return candidate

    # Pattern 2: message contains "branch" + a branch-like token
    if "branch" in text_lower:
        tokens = text.split()
        for token in reversed(tokens):
            cleaned = token.strip("'\"` .,!?")
            if is_valid_branch_name(cleaned) and cleaned.lower() != "branch":
                return cleaned

    # Pattern 3: short message (≤3 words) with a branch-like token
    tokens = text.split()
    if len(tokens) <= 3:
        for token in reversed(tokens):
            cleaned = token.strip("'\"` .,!?")
            if is_valid_branch_name(cleaned):
                return cleaned

    return None
