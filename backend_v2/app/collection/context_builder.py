"""
Context builder — constructs minimal LLM context for extraction/formatting.
Only includes fields relevant to the current ask. Keeps token usage low.
"""
from app.models import FieldSpec
from app.collection.planner import CollectionPlan


def build_extraction_context(plan: CollectionPlan, known_fields: dict[str, dict]) -> str:
    """Build context for the extractor LLM: what fields to look for across all resources."""
    lines = []

    # Show what's already known per resource (keyed by resource_id)
    if known_fields:
        lines.append("Already known values:")
        for resource_id, fields in known_fields.items():
            if fields:
                lines.append(f"  [{resource_id}]: {', '.join(f'{k}={v}' for k, v in fields.items())}")
        lines.append("")

    # Shared fields (ask once, apply to all)
    if plan.shared_fields:
        lines.append("SHARED fields (same value applies to all resources — ask if same or different):")
        for spec in plan.shared_fields:
            line = f"  - {spec.name}: {spec.description}"
            if spec.options:
                line += f" [options: {', '.join(spec.options)}]"
            elif spec.validation:
                line += f" [rule: {spec.validation}]"
            lines.append(line)
        lines.append("")

    # Per-resource fields (keyed by resource_id)
    if plan.per_resource:
        for resource_id, specs in plan.per_resource.items():
            lines.append(f"Fields specific to {resource_id}:")
            for spec in specs:
                line = f"  - {spec.name}: {spec.description}"
                if spec.options:
                    line += f" [options: {', '.join(spec.options)}]"
                elif spec.validation:
                    line += f" [rule: {spec.validation}]"
                lines.append(line)
            lines.append("")

    return "\n".join(lines)


def build_format_context(plan: CollectionPlan, known_fields: dict[str, dict], errors: dict) -> str:
    """Build context for the formatter LLM: what to ask the user about."""
    lines = []
    
    # What resources are being built (resource_ids)
    resource_ids = list(plan.per_resource.keys())
    if plan.shared_fields:
        resource_ids = list(set(resource_ids + list(known_fields.keys())))
    if resource_ids:
        lines.append(f"Resources being configured: {', '.join(resource_ids)}")
        lines.append("")

    # Show what's already known (keyed by resource_id)
    if known_fields:
        lines.append("Values already collected:")
        for resource_id, fields in known_fields.items():
            if fields:
                lines.append(f"  [{resource_id}]:")
                for k, v in fields.items():
                    lines.append(f"    ✓ {k}: {v}")
        lines.append("")

    if errors:
        lines.append("Values that need correction:")
        for name, issue in errors.items():
            lines.append(f"  ✗ {name}: {issue}")
        lines.append("")

    # Shared fields
    if plan.shared_fields:
        lines.append("SHARED fields (needed by all resources — ask user if it's the same for all or different):")
        for spec in plan.shared_fields:
            parts = [f"  - {spec.name}: {spec.description}"]
            if spec.options:
                parts.append(f"\n    Options: {', '.join(spec.options)}")
            elif spec.validation:
                parts.append(f"\n    Rule: {spec.validation}")
            lines.append("".join(parts))
        lines.append("")

    # Per-resource fields (keyed by resource_id)
    if plan.per_resource:
        for resource_id, specs in plan.per_resource.items():
            lines.append(f"Fields for {resource_id}:")
            for spec in specs:
                parts = [f"  - {spec.name}: {spec.description}"]
                if spec.options:
                    parts.append(f"\n    Options: {', '.join(spec.options)}")
                elif spec.validation:
                    parts.append(f"\n    Rule: {spec.validation}")
                lines.append("".join(parts))
            lines.append("")

    return "\n".join(lines)
