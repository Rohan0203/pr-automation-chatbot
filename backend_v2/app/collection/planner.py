"""
Collector — pure logic, no LLM.
Determines which fields are askable right now for a resource.
Groups fields across multiple resources into shared vs per-resource.
"""
from app.models import Resource, FieldSpec
from app.collection.spec_registry import get_field_specs
from dataclasses import dataclass


@dataclass
class CollectionPlan:
    """What to ask the user — grouped by shared and per-resource."""
    shared_fields: list[FieldSpec]                        # Same field name across 2+ resource instances
    per_resource: dict[str, list[FieldSpec]]              # resource_id → unique fields
    all_done: bool                                        # True if nothing left to collect


def get_askable_fields(resource: Resource) -> list[FieldSpec]:
    """
    Returns fields that can be asked right now:
    - Not already filled
    - Not derivable
    - Dependencies satisfied (if any)
    """
    specs = get_field_specs(resource.resource_type)
    askable = []

    for spec in specs:
        if spec.name in resource.fields:
            continue
        if spec.derivable:
            continue
        if spec.depends_on:
            dep_met = all(
                resource.fields.get(dep_field) == dep_value
                for dep_field, dep_value in spec.depends_on.items()
            )
            if not dep_met:
                dep_blocked = any(
                    dep_field in resource.fields and resource.fields[dep_field] != dep_value
                    for dep_field, dep_value in spec.depends_on.items()
                )
                if dep_blocked:
                    continue
                continue

        askable.append(spec)

    return askable


def build_collection_plan(resources: list[Resource]) -> CollectionPlan:
    """
    Look at ALL resources, find what's missing, and group into:
    - shared: fields with the same name needed by 2+ resources
    - per_resource: fields unique to one resource type
    """
    # Get askable fields per resource (keyed by resource_id for instance uniqueness)
    per_resource_askable: dict[str, list[FieldSpec]] = {}
    for r in resources:
        if r.status.value in ("done", "dropped"):
            continue
        askable = get_askable_fields(r)
        if askable:
            per_resource_askable[r.resource_id] = askable

    if not per_resource_askable:
        return CollectionPlan(shared_fields=[], per_resource={}, all_done=True)

    # If only one resource instance, everything is "per_resource" (no sharing)
    if len(per_resource_askable) == 1:
        return CollectionPlan(
            shared_fields=[],
            per_resource=per_resource_askable,
            all_done=False,
        )

    # Find shared field names (same name appears in 2+ resource instances)
    field_name_count: dict[str, int] = {}
    field_name_to_spec: dict[str, FieldSpec] = {}
    for rid, specs in per_resource_askable.items():
        for spec in specs:
            field_name_count[spec.name] = field_name_count.get(spec.name, 0) + 1
            field_name_to_spec[spec.name] = spec

    shared_names = {name for name, count in field_name_count.items() if count > 1}

    # Build shared list
    shared_fields = [field_name_to_spec[name] for name in shared_names]

    # Build per-resource (only fields NOT in shared)
    per_resource_unique: dict[str, list[FieldSpec]] = {}
    for rid, specs in per_resource_askable.items():
        unique = [s for s in specs if s.name not in shared_names]
        if unique:
            per_resource_unique[rid] = unique

    return CollectionPlan(
        shared_fields=shared_fields,
        per_resource=per_resource_unique,
        all_done=False,
    )


def is_collection_complete(resource: Resource) -> bool:
    """Check if all required non-derivable fields are filled."""
    specs = get_field_specs(resource.resource_type)

    for spec in specs:
        if spec.derivable:
            continue
        if not spec.required:
            continue
        if spec.name in resource.fields:
            continue
        if spec.depends_on:
            dep_blocked = any(
                dep_field in resource.fields and resource.fields[dep_field] != dep_value
                for dep_field, dep_value in spec.depends_on.items()
            )
            if dep_blocked:
                continue
        return False

    return True
