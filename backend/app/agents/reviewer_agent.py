"""
Reviewer Agent — Validates generated YAML against organizational policy rules.

DESIGN:
- Loads all validation MD files from data/s3-bucket-validations/ at startup.
- Concatenates them into a single context string per resource type.
- On review, sends the YAML + validation context to the LLM.
- Returns a structured ReviewResult (pass/fail + typed violations).

Separation of concerns:
  Generator Agent → "Is each field individually valid? Can I produce well-formed YAML?"
  Reviewer Agent  → "Does this YAML comply with organizational policy?"

The reviewer runs ONCE on the final confirmed YAML, before PR creation.
It does NOT modify the YAML — it only flags violations.
"""
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.config import DATA_DIR
from app.services.llm_client import llm_client
from app.agents.prompts import REVIEWER_SYSTEM_PROMPT, REVIEWER_PROMPT

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# VALIDATION CONTEXT DIRECTORIES
# Each resource type has its own folder of validation MD files.
# ═══════════════════════════════════════════════════════════════

VALIDATION_DIRS: dict[str, str] = {
    "s3": "s3-bucket-validations",
    "glue_db": "gluedb-validations",
}


# ═══════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════

@dataclass
class ReviewViolation:
    """A single root-cause violation found during review."""
    fields: list[str]        # e.g. ["aws_account_id", "database_s3_location"]
    rules: list[str]         # e.g. ["ACC-001", "S3-001"]
    severity: str            # "error" | "warning"
    root_cause: str          # Plain-language explanation of the core problem
    fix_options: list[dict]  # Each: {"label": "...", "changes": {"field": "value"}}

    # Legacy single-field accessors for backward compatibility
    @property
    def field(self) -> str:
        return self.fields[0] if self.fields else "unknown"

    @property
    def rule(self) -> str:
        return ", ".join(self.rules) if self.rules else "unknown"

    @property
    def message(self) -> str:
        return self.root_cause

    @property
    def suggestion(self) -> str:
        if self.fix_options:
            opt = self.fix_options[0]
            changes = opt.get("changes", {})
            return "; ".join(f"{k} → {v}" for k, v in changes.items())
        return ""


@dataclass
class ReviewResult:
    """Result of a YAML review against organizational policy."""
    passed: bool                         # True if no ERROR-level violations
    violations: list[ReviewViolation] = field(default_factory=list)
    summary: str = ""                    # One-line summary for the user

    @property
    def errors(self) -> list[ReviewViolation]:
        return [v for v in self.violations if v.severity == "error"]

    @property
    def warnings(self) -> list[ReviewViolation]:
        return [v for v in self.violations if v.severity == "warning"]

    def to_dict(self) -> dict:
        """Serialize for API response."""
        return {
            "passed": self.passed,
            "summary": self.summary,
            "violations": [
                {
                    "fields": v.fields,
                    "rules": v.rules,
                    "severity": v.severity,
                    "root_cause": v.root_cause,
                    "fix_options": v.fix_options,
                }
                for v in self.violations
            ],
        }


# ═══════════════════════════════════════════════════════════════
# REVIEWER AGENT
# ═══════════════════════════════════════════════════════════════

class ReviewerAgent:
    """
    Validates YAML configurations against organizational policy rules
    defined in Markdown files. Uses a single LLM call with all rules
    concatenated as context.
    """

    def __init__(self):
        self._contexts: dict[str, str] = {}  # resource_type → concatenated MD content

    def load(self):
        """Load validation MD files for all resource types at startup."""
        for rtype, dirname in VALIDATION_DIRS.items():
            dir_path = DATA_DIR / dirname
            if not dir_path.exists():
                logger.warning(f"Validation rules directory not found: {dir_path}")
                continue

            parts = []
            md_files = sorted(dir_path.glob("*.md"))

            if not md_files:
                logger.warning(f"No MD files found in {dir_path}")
                continue

            for md_file in md_files:
                content = md_file.read_text(encoding="utf-8").strip()
                if content:
                    # Add a header so the LLM knows which file each section comes from
                    parts.append(f"## FILE: {md_file.name}\n\n{content}")

            combined = "\n\n---\n\n".join(parts)
            self._contexts[rtype] = combined
            logger.info(
                f"Loaded {len(md_files)} validation rule files for '{rtype}' "
                f"({len(combined)} chars)"
            )

    def get_supported_types(self) -> list[str]:
        """Return resource types that have validation rules loaded."""
        return list(self._contexts.keys())

    def has_rules(self, resource_type: str) -> bool:
        """Check if validation rules exist for a resource type."""
        return resource_type in self._contexts

    async def review(self, yaml_content: str, resource_type: str) -> ReviewResult:
        """
        Review a YAML configuration against organizational policy rules.

        Args:
            yaml_content: The complete YAML string to review.
            resource_type: e.g. "s3", "glue_db", "iam"

        Returns:
            ReviewResult with pass/fail status and any violations.
        """
        validation_context = self._contexts.get(resource_type)

        if not validation_context:
            logger.info(f"No validation rules for '{resource_type}' — skipping review")
            return ReviewResult(
                passed=True,
                summary=f"No organizational review rules configured for {resource_type}.",
            )

        # Build the reviewer prompt
        prompt = REVIEWER_PROMPT.format(
            resource_type=resource_type,
            validation_context=validation_context,
            yaml_content=yaml_content,
        )

        messages = [
            {"role": "system", "content": REVIEWER_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        try:
            result = await llm_client.extract_json(messages, temperature=0.0)
        except Exception as e:
            logger.error(f"Reviewer LLM call failed: {e}", exc_info=True)
            # On LLM failure, don't block — pass with a warning
            return ReviewResult(
                passed=True,
                summary="Review could not be completed (LLM error). Proceeding with caution.",
                violations=[
                    ReviewViolation(
                        fields=[""],
                        rules=["review-unavailable"],
                        severity="warning",
                        root_cause=f"Automated review failed: {str(e)}. Manual review recommended.",
                        fix_options=[],
                    )
                ],
            )

        return self._parse_result(result)

    def _parse_result(self, raw: dict) -> ReviewResult:
        """Parse the LLM JSON response into a ReviewResult."""
        violations = []

        for v in raw.get("violations", []):
            if not isinstance(v, dict):
                continue

            # Support new format (fields/rules/root_cause/fix_options)
            # and legacy format (field/rule/message/suggestion)
            fields = v.get("fields") or [v.get("field", "unknown")]
            rules = v.get("rules") or [v.get("rule", "unknown")]
            root_cause = v.get("root_cause") or v.get("message", "")
            fix_options = v.get("fix_options") or []

            # ── Safety filter: skip entries that are really "passing" notes ──
            _rc_lower = root_cause.lower()
            _skip_phrases = [
                "no violation", "no issue", "is correct", "is valid",
                "passes", "complies", "properly set", "matches",
                "all rules pass", "correctly configured", "no error",
            ]
            if any(phrase in _rc_lower for phrase in _skip_phrases):
                continue

            # If legacy format with single suggestion, convert
            if not fix_options and v.get("suggestion"):
                fix_options = [{"label": "Suggested fix", "changes": {fields[0]: v["suggestion"]}}]

            violations.append(
                ReviewViolation(
                    fields=fields if isinstance(fields, list) else [fields],
                    rules=rules if isinstance(rules, list) else [rules],
                    severity=v.get("severity", "warning").lower(),
                    root_cause=root_cause,
                    fix_options=fix_options,
                )
            )

        # Determine pass/fail: any ERROR-level violation → fail
        has_errors = any(v.severity == "error" for v in violations)

        return ReviewResult(
            passed=not has_errors,
            violations=violations,
            summary=raw.get("summary", "Review complete."),
        )


# ── Singleton ─────────────────────────────────────────────────

reviewer_agent = ReviewerAgent()
