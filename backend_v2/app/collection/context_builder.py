"""
Context builder — constructs minimal LLM context for extraction/formatting.
Only includes fields relevant to the current ask. Keeps token usage low.
"""
from app.models import FieldSpec
from app.collection.planner import CollectionPlan


def build_extraction_context(plan: CollectionPlan, known_fields: dict[str, dict]) -> str:
    """Build context for the extractor LLM: what fields to look for across all resources."""
    lines = []

    # Show what's already known per resource
    if known_fields:
        lines.append("Already known values:")
        for rtype, fields in known_fields.items():
            if fields:
                lines.append(f"  [{rtype}]: {', '.join(f'{k}={v}' for k, v in fields.items())}")
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

    # Per-resource fields
    if plan.per_resource:
        for rtype, specs in plan.per_resource.items():
            lines.append(f"Fields specific to {rtype}:")
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
    
    # What resources are being built
    resource_types = list(plan.per_resource.keys())
    if plan.shared_fields:
        # Get all resource types from known_fields too
        resource_types = list(set(resource_types + list(known_fields.keys())))
    if resource_types:
        lines.append(f"Resources being configured: {', '.join(resource_types)}")
        lines.append("")

    # Show what's already known
    if known_fields:
        lines.append("Values already collected:")
        for rtype, fields in known_fields.items():
            if fields:
                for k, v in fields.items():
                    lines.append(f"  ✓ {k}: {v}")
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

    # Per-resource fields
    if plan.per_resource:
        for rtype, specs in plan.per_resource.items():
            lines.append(f"Fields for {rtype} only:")
            for spec in specs:
                parts = [f"  - {spec.name}: {spec.description}"]
                if spec.options:
                    parts.append(f"\n    Options: {', '.join(spec.options)}")
                elif spec.validation:
                    parts.append(f"\n    Rule: {spec.validation}")
                lines.append("".join(parts))
            lines.append("")

    return "\n".join(lines)
