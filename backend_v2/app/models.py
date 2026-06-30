"""
State models — the single source of truth for "where are we?"

SessionMode: what the session is doing right now.
ResourceStatus: per-resource lifecycle stage.
Resource: one resource being built.
Session: the full user session.
FieldSpec: definition of one field in a resource schema.
"""
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Any


class SessionMode(str, Enum):
    IDLE = "idle"             # Waiting for user to say what they want
    WORKING = "working"       # Processing resources (collection loop)


class ResourceStatus(str, Enum):
    PENDING = "pending"       # Detected, not yet started collection
    COLLECTING = "collecting" # Gathering field values
    CONFIRMING = "confirming" # Showing extracted values for user to confirm
    DONE = "done"             # All fields collected and confirmed
    BLOCKED = "blocked"       # Stuck — retry threshold exceeded
    DROPPED = "dropped"       # User abandoned this resource


@dataclass
class FieldSpec:
    """Definition of one field in a resource schema."""
    name: str
    required: bool = True
    description: str = ""                       # Help text shown to user
    options: list[str] | None = None            # Constrained values (None = free text)
    validation: str | None = None               # Rule description for LLM
    depends_on: dict[str, Any] | None = None    # e.g. {"data_construct": "Source"}
    derivable: bool = False                     # True = auto-computed, never ask
    default: str | None = None                  # Pre-fill if user doesn't specify


@dataclass
class Resource:
    """A single resource being built."""
    resource_id: str                            # Unique instance ID (e.g. "s3_0", "glue_db_1")
    resource_type: str                          # Schema type key (e.g. "s3", "glue_db")
    status: ResourceStatus = ResourceStatus.PENDING
    fields: dict[str, Any] = field(default_factory=dict)  # All known values (filled progressively)
    retry_counts: dict[str, int] = field(default_factory=dict)  # Per-field extraction failure count
    yaml_output: Optional[str] = None


@dataclass
class Session:
    """Full user session state."""
    session_id: str
    mode: SessionMode = SessionMode.IDLE
    resources: list[Resource] = field(default_factory=list)
    active_resource_idx: int = 0
    history: list[dict] = field(default_factory=list)
    _flushed_idx: int = field(default=0, repr=False)  # messages already persisted

    @property
    def active_resource(self) -> Optional[Resource]:
        if 0 <= self.active_resource_idx < len(self.resources):
            return self.resources[self.active_resource_idx]
        return None

    def add_message(self, role: str, content: str):
        self.history.append({"role": role, "content": content})

    def next_pending_resource(self) -> Optional[int]:
        """Find next resource that needs work."""
        for i, r in enumerate(self.resources):
            if r.status in (ResourceStatus.PENDING, ResourceStatus.COLLECTING):
                return i
        return None

    def all_done(self) -> bool:
        return all(r.status in (ResourceStatus.DONE, ResourceStatus.DROPPED) for r in self.resources)

    def dump(self) -> dict:
        return {
            "session_id": self.session_id,
            "mode": self.mode.value,
            "active_resource_idx": self.active_resource_idx,
            "resources": [
                {
                    "id": r.resource_id,
                    "type": r.resource_type,
                    "status": r.status.value,
                    "fields": r.fields,
                    "retries": r.retry_counts,
                    "has_yaml": r.yaml_output is not None,
                }
                for r in self.resources
            ],
            "history_len": len(self.history),
        }
