"""
Structured Flow Handler — manages the guided Q1→Q2→Q3→text_collection→finalize flow.

This is the button-driven guided experience that walks users through:
  Q1: Environment (dev/prd)
  Q2: Resource type(s) + Enterprise
  Q3: Conditional questions (subgroup, account placement, CDP flag, serving purpose)
  Text Collection: Remaining free-text fields
  Finalization: Derive fields, generate YAMLs, show combined preview

Extracted from the monolithic GeneratorAgent.
"""
import re
import json
import logging
from typing import Optional

from app.agents.session_state import (
    AgentState,
    SessionState,
    StructuredFlow,
    RESOURCE_OPTIONS,
    ENTERPRISE_SUBGROUPS,
)
from app.agents.response_decorator import build_response
from app.agents.yaml_utils import generate_yaml
from app.agents.field_deriver import derive_s3_fields, derive_glue_db_fields
from app.services.llm_client import llm_client
from app.services.schema_registry import schema_registry

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def start_structured_flow(
    session: SessionState,
    detected_type: str = None,
    extracted_fields: dict = None,
) -> dict:
    """Start the guided Q1→Q2→Q3 flow. Returns Q1 prompt."""
    logger.info("[FLOW] start_structured_flow: detected_type=%s, extracted_keys=%s",
                detected_type, list(extracted_fields.keys()) if extracted_fields else [])
    flow = StructuredFlow()
    session.structured_flow = flow

    if extracted_fields and detected_type:
        _prefill_flow_from_extracted(flow, detected_type, extracted_fields)
        if flow.environment:
            flow.phase = "q2_resource"
            return _present_q2_resources(session)

    return _present_q1_environment(session)


# ═══════════════════════════════════════════════════════════════
# MAIN DISPATCHER
# ═══════════════════════════════════════════════════════════════

async def handle_structured_flow(
    session: SessionState,
    user_message: str,
    build_messages_fn,
) -> dict:
    """Dispatch to the current structured flow phase."""
    flow = session.structured_flow
    msg_lower = user_message.strip().lower()

    logger.info("[FLOW] handle_structured_flow: phase=%s, user_msg=%.80s",
                flow.phase if flow else 'None', user_message[:80].replace('\n', ' '))

    if msg_lower in {"cancel", "stop", "quit", "abort", "exit"}:
        session.structured_flow = None
        return build_response("Setup cancelled. Let me know if you'd like to start over.")

    if msg_lower in {"restart", "start over", "reset"}:
        session.structured_flow = None
        return start_structured_flow(session)

    if msg_lower in {"back", "go back", "previous", "change", "undo"}:
        return await _handle_go_back(session)

    reject_patterns = [
        "don't want", "dont want", "not that", "wrong", "no i",
        "change resource", "different resource", "not what i",
        "i said", "that's not", "thats not", "i meant",
    ]
    if any(p in msg_lower for p in reject_patterns):
        return await _handle_go_back(session)

    if flow.phase == "q1_env":
        logger.info("[FLOW] → q1_env handler")
        return _handle_q1_response(session, user_message)
    elif flow.phase == "q2_resource":
        logger.info("[FLOW] → q2_resource handler")
        return _handle_q2_resource_response(session, user_message)
    elif flow.phase == "q2_enterprise":
        logger.info("[FLOW] → q2_enterprise handler")
        return await _handle_q2_enterprise_response(session, user_message)
    elif flow.phase == "q3_conditionals":
        logger.info("[FLOW] → q3_conditionals handler")
        return await _handle_q3_response(session, user_message)
    elif flow.phase == "classification":
        logger.info("[FLOW] → classification handler")
        return await _handle_classification_response(session, user_message)
    elif flow.phase == "text_collection":
        logger.info("[FLOW] → text_collection handler")
        return await _handle_text_collection_response(session, user_message, build_messages_fn)
    else:
        logger.info("[FLOW] → unknown phase=%s, restarting flow", flow.phase)
        session.structured_flow = None
        return start_structured_flow(session)


# ═══════════════════════════════════════════════════════════════
# Q1 — ENVIRONMENT
# ═══════════════════════════════════════════════════════════════

def _present_q1_environment(session: SessionState) -> dict:
    session.structured_flow.phase = "q1_env"
    return build_response(
        "**Step 1 of 3** — Which environment is this for?",
        resource_status="q1_env",
        options=[
            {"label": "🔧 Dev", "value": "dev", "description": "Development environment"},
            {"label": "🚀 Prod", "value": "prd", "description": "Production environment"},
        ],
    )


def _handle_q1_response(session: SessionState, user_message: str) -> dict:
    flow = session.structured_flow
    msg = user_message.strip().lower()

    if "dev" in msg:
        flow.environment = "dev"
    elif "prd" in msg or "prod" in msg:
        flow.environment = "prd"
    else:
        return build_response(
            "Please select an environment:",
            resource_status="q1_env",
            options=[
                {"label": "🔧 Dev", "value": "dev"},
                {"label": "🚀 Prod", "value": "prd"},
            ],
        )

    return _present_q2_resources(session)


# ═══════════════════════════════════════════════════════════════
# Q2 — RESOURCE TYPE + ENTERPRISE
# ═══════════════════════════════════════════════════════════════

def _present_q2_resources(session: SessionState) -> dict:
    flow = session.structured_flow
    flow.phase = "q2_resource"
    env_label = "Dev" if flow.environment == "dev" else "Prod"

    return build_response(
        f"**Step 2 of 3** — Environment: **{env_label}**\n\n"
        f"What type of resource(s) do you need?\n"
        f"*You can select **multiple** resources — e.g. an S3 bucket and a Glue DB together.*",
        resource_status="q2_resource",
        options=_build_resource_options(),
        options_multi_select=True,
    )


def _handle_q2_resource_response(session: SessionState, user_message: str) -> dict:
    flow = session.structured_flow
    msg = user_message.strip().lower()

    parts = [p.strip() for p in msg.split(",") if p.strip()]
    resolved_keys = []
    for part in parts:
        key = _resolve_resource_key(part)
        if key and key not in resolved_keys:
            resolved_keys.append(key)

    if not resolved_keys:
        return build_response(
            "I didn't recognize that resource type. Please select one or more options below:",
            resource_status="q2_resource",
            options=_build_resource_options(),
            options_multi_select=True,
        )

    flow.selected_resources = resolved_keys
    flow.current_resource_index = 0
    flow.selected_resource = resolved_keys[0]

    return _present_q2_enterprise(session)


def _present_q2_enterprise(session: SessionState) -> dict:
    flow = session.structured_flow
    flow.phase = "q2_enterprise"

    if len(flow.selected_resources) > 1:
        labels = [
            RESOURCE_OPTIONS[k]["label"]
            for k in flow.selected_resources
            if k in RESOURCE_OPTIONS
        ]
        resources_text = ", ".join(labels)
        prompt = f"Which enterprise are these resources for?\n\n📋 Selected: **{resources_text}**"
    else:
        config = flow.get_resource_config()
        resource_label = config.get("label", "resource")
        prompt = f"Which enterprise is this **{resource_label}** for?"

    return build_response(
        prompt,
        resource_status="q2_enterprise",
        options=[
            {"label": "AGTR", "value": "AGTR", "description": "Ag Trading"},
            {"label": "CORP", "value": "CORP", "description": "Corporate"},
            {"label": "FOOD", "value": "FOOD", "description": "Food"},
            {"label": "SPEC", "value": "SPEC", "description": "Specialized"},
            {"label": "⬅️ Go Back", "value": "back", "description": "Change resource type"},
        ],
    )


async def _handle_q2_enterprise_response(session: SessionState, user_message: str) -> dict:
    flow = session.structured_flow
    msg = user_message.strip().upper()

    enterprise = None
    for ent in ("AGTR", "CORP", "FOOD", "SPEC"):
        if ent in msg:
            enterprise = ent
            break

    if not enterprise:
        fuzzy_ent = {
            "ag trading": "AGTR", "agriculture": "AGTR",
            "corporate": "CORP",
            "specialized": "SPEC", "specialty": "SPEC",
        }
        msg_lower = user_message.strip().lower()
        for phrase, ent in fuzzy_ent.items():
            if phrase in msg_lower:
                enterprise = ent
                break

    if not enterprise:
        return _present_q2_enterprise(session)

    flow.selected_enterprise = enterprise
    flow.compute_q3_questions()
    return await _present_q3(session)


# ═══════════════════════════════════════════════════════════════
# Q3 — CONDITIONAL QUESTIONS
# ═══════════════════════════════════════════════════════════════

async def _present_q3(session: SessionState) -> dict:
    flow = session.structured_flow
    flow.phase = "q3_conditionals"

    q = flow.current_q3_question()
    if q is None:
        if flow.has_glue_resources():
            return _present_classification(session)
        return _present_combined_text_collection(session)

    res_key = flow.q3_resource_context.get(q)
    res_label = RESOURCE_OPTIONS.get(res_key, {}).get("label", "") if res_key else ""
    context_note = f" *(for {res_label})*" if res_label else ""

    if q == "account_placement":
        return build_response(
            f"Where should the resource be placed?{context_note}",
            resource_status="q3_conditionals",
            options=[
                {"label": "🏠 Lakehouse", "value": "lakehouse", "description": "Shared data lake account"},
                {"label": "⚡ Compute", "value": "compute", "description": "Enterprise-specific compute account"},
            ],
        )

    if q == "data_construct":
        return build_response(
            f"Is this Internal DB for a **Source** system or a **DataProduct**?{context_note}",
            resource_status="q3_conditionals",
            options=[
                {"label": "Source", "value": "Source", "description": "Internal DB for a source system (→ Lakehouse)"},
                {"label": "DataProduct", "value": "DataProduct", "description": "Internal DB for a data product (→ Compute)"},
            ],
        )

    if q == "cdp_flag":
        return build_response(
            "Raw Source Glue DB — current or CDP data?",
            resource_status="q3_conditionals",
            options=[
                {"label": "Current", "value": "no", "description": "Current / standard source"},
                {"label": "CDP", "value": "yes", "description": "Customer Data Platform source"},
            ],
        )

    if q == "serving_purpose":
        return build_response(
            f"Serving purpose for the Serving DB?{context_note}\n\n"
            "This becomes part of the database name (e.g. `_serving_analytics_dev`).",
            resource_status="q3_conditionals",
            options=[
                {"label": "Analytics", "value": "analytics"},
                {"label": "Reporting", "value": "reporting"},
                {"label": "Events", "value": "events"},
                {"label": "API", "value": "api"},
                {"label": "Other (type below)", "value": "__custom__"},
            ],
        )

    if q == "subgroup":
        enterprise = flow.selected_enterprise
        subgroups = ENTERPRISE_SUBGROUPS.get(enterprise, [])
        options = [{"label": "None / Skip", "value": "", "description": "No subgroup"}]
        for sg in subgroups:
            options.append({"label": sg, "value": sg})

        return build_response(
            f"Which {enterprise} subgroup?",
            resource_status="q3_conditionals",
            options=options,
        )

    # Unknown — skip
    flow.advance_q3()
    return await _present_q3(session)


async def _handle_q3_response(session: SessionState, user_message: str) -> dict:
    flow = session.structured_flow
    q = flow.current_q3_question()
    msg = user_message.strip().lower()

    if q == "account_placement":
        if "lakehouse" in msg or "lh" in msg:
            flow.account_placement = "lakehouse"
        elif "compute" in msg or "cmp" in msg:
            flow.account_placement = "compute"
        else:
            return await _present_q3(session)

    elif q == "data_construct":
        if "source" in msg:
            flow.data_construct = "Source"
        elif "dataproduct" in msg or "data product" in msg or "product" in msg:
            flow.data_construct = "DataProduct"
        else:
            return await _present_q3(session)

    elif q == "cdp_flag":
        if "yes" in msg or "cdp" in msg:
            flow.cdp_flag = "yes"
        else:
            flow.cdp_flag = "no"

    elif q == "serving_purpose":
        if "__custom__" in msg:
            return build_response(
                "Please type the serving purpose (e.g. `analytics`, `reporting`, `events`):",
                resource_status="q3_conditionals",
            )
        purpose = user_message.strip().lower().replace(" ", "_")
        if purpose:
            flow.serving_purpose = purpose
        else:
            return await _present_q3(session)

    elif q == "subgroup":
        value = user_message.strip().upper()
        if value in ("NONE", "SKIP", "NONE / SKIP", ""):
            flow.subgroup = ""
        elif value:
            enterprise = flow.selected_enterprise
            valid_sgs = ENTERPRISE_SUBGROUPS.get(enterprise, [])
            if value in valid_sgs or not valid_sgs:
                flow.subgroup = value
            else:
                return build_response(
                    f"**{value}** is not a valid subgroup for {enterprise}.\n\n"
                    f"Valid options: {', '.join(valid_sgs)}",
                    resource_status="q3_conditionals",
                    options=[{"label": sg, "value": sg} for sg in valid_sgs]
                    + [{"label": "None / Skip", "value": ""}],
                )
        else:
            flow.subgroup = ""

    flow.advance_q3()
    return await _present_q3(session)


# ═══════════════════════════════════════════════════════════════
# CLASSIFICATION
# ═══════════════════════════════════════════════════════════════

def _present_classification(session: SessionState) -> dict:
    flow = session.structured_flow
    flow.phase = "classification"
    flow._classif_step = "classification"

    return build_response(
        "Data classification for the Glue databases?",
        resource_status="classification",
        options=[
            {"label": "Confidential - General Use", "value": "Confidential - General Use",
             "description": "Default — most common"},
            {"label": "Confidential - Limited", "value": "Confidential - Limited",
             "description": "Restricted access"},
            {"label": "Confidential - Restricted", "value": "Confidential - Restricted",
             "description": "Highly restricted"},
            {"label": "Internal", "value": "Internal", "description": "Internal use only"},
        ],
    )


async def _handle_classification_response(session: SessionState, user_message: str) -> dict:
    flow = session.structured_flow
    flow.data_classification = user_message.strip()
    return _present_combined_text_collection(session)


# ═══════════════════════════════════════════════════════════════
# TEXT COLLECTION
# ═══════════════════════════════════════════════════════════════

def _present_combined_text_collection(session: SessionState) -> dict:
    flow = session.structured_flow
    flow.phase = "text_collection"

    needed = []
    has_s3 = False
    has_glue_source = False
    has_glue_product = False
    has_glue_serving = False
    has_glue = False

    for res_key in flow.selected_resources:
        config = RESOURCE_OPTIONS.get(res_key, {})
        rtype = config.get("resource_type")
        auto = config.get("auto_fields", {})

        if rtype == "s3":
            has_s3 = True
        elif rtype == "glue_db":
            has_glue = True
            construct = auto.get("data_construct", "")
            layer = auto.get("data_layer", "")
            if construct == "Source" or layer == "raw":
                has_glue_source = True
            if construct == "DataProduct" or layer in ("curated", "serving"):
                has_glue_product = True
            if layer == "serving":
                has_glue_serving = True

    if has_glue_source:
        needed.append("**Source name** for the Raw Glue DB (e.g. `sap`, `concur`, `workday`)")
    if has_glue_product:
        needed.append("**Data product name** for the Serving/Curated Glue DB (e.g. `c360`, `controls`)")
    if has_glue_serving and not flow.serving_purpose:
        needed.append("**Serving purpose** (e.g. `analytics`, `reporting`, `consumption`)")
    if has_glue:
        needed.append("**Data privacy**: `PI`, `PCI`, `PHI`, `BCI`, or `NONE`")
        needed.append("**Data owner email**")
        needed.append("**Data owner GitHub username**")
        needed.append("**Data leader** (e.g. `KatiePorter`, `a123456`)")

    total = len(flow.selected_resources)
    resource_labels = [
        RESOURCE_OPTIONS.get(k, {}).get("label", k) for k in flow.selected_resources
    ]
    resource_list = ", ".join(resource_labels)
    needed.append(
        f"**Intake IDs** — {total} resource{'s' if total > 1 else ''} total "
        f"({resource_list}). How many IDs and how do they map?"
    )

    fields_list = "\n".join(f"  • {f}" for f in needed)

    return build_response(
        f"**Last details:**\n\n{fields_list}",
        resource_status="text_collection",
    )


async def _handle_text_collection_response(
    session: SessionState,
    user_message: str,
    build_messages_fn,
) -> dict:
    flow = session.structured_flow
    flow._tc_raw_text = user_message
    return await _finalize_all_resources(session, build_messages_fn)


# ═══════════════════════════════════════════════════════════════
# FINALIZATION — derive fields, generate YAMLs, show preview
# ═══════════════════════════════════════════════════════════════

async def _finalize_all_resources(session: SessionState, build_messages_fn) -> dict:
    flow = session.structured_flow
    raw_text = getattr(flow, "_tc_raw_text", "")

    parsed = await _parse_combined_input(flow, raw_text)

    for res_key in flow.selected_resources:
        config = RESOURCE_OPTIONS.get(res_key, {})
        resource_type = config.get("resource_type", "s3")

        auto_fields = flow.build_auto_fields_for(res_key)

        if resource_type == "s3":
            auto_fields.setdefault("aws_region", "us-east-1")
            auto_fields.setdefault(
                "versioning_enabled", "true" if res_key == "s3_scripts" else "false"
            )
        else:
            auto_fields.setdefault("region", "us-east-1")
            if flow.data_classification:
                auto_fields["data_classification"] = flow.data_classification
            else:
                auto_fields.setdefault("data_classification", "Confidential - General Use")

        res_parsed = parsed.get(res_key, {})
        for k, v in res_parsed.items():
            if v:
                auto_fields[k] = v

        shared = parsed.get("_shared", {})
        if resource_type == "glue_db":
            for k in ("data_privacy", "data_owner_email", "data_owner_github_uname", "data_leader"):
                if k in shared and shared[k]:
                    auto_fields.setdefault(k, shared[k])
            if not auto_fields.get("data_privacy"):
                auto_fields["data_privacy"] = "NONE"

        agent = session.start_new_resource()
        agent.resource_type = resource_type
        agent.collected_fields = auto_fields
        agent.phase = "collecting"
        agent.initial_listing_shown = True
        agent.optional_fields_offered = True

        flow.selected_resource = res_key
        _derive_account_from_flow(flow, agent)

        if resource_type == "s3":
            derived = derive_s3_fields(agent.collected_fields)
            for k, v in derived.items():
                agent.collected_fields.setdefault(k, v)
            if "bucket_description" not in agent.collected_fields:
                agent.collected_fields["bucket_description"] = _generate_bucket_description(flow, res_key)
        else:
            derived = derive_glue_db_fields(agent.collected_fields)
            for k, v in derived.items():
                agent.collected_fields.setdefault(k, v)
            if "database_description" not in agent.collected_fields:
                agent.collected_fields["database_description"] = _generate_db_description(flow, res_key, agent)

        yaml_result = await generate_yaml(session, agent, build_messages_fn, silent=True)
        if not yaml_result:
            logger.warning(f"YAML generation failed for {res_key} — LLM unreachable or returned empty")
            yaml_result = None  # Mark as failed, handle in preview

        flow.completed_resource_yamls.append({
            "resource_key": res_key,
            "resource_type": resource_type,
            "label": RESOURCE_OPTIONS.get(res_key, {}).get("label", res_key),
            "fields": agent.collected_fields.copy(),
            "yaml": yaml_result,
        })

    return _show_multi_yaml_preview(session, flow)


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def _prefill_flow_from_extracted(flow: StructuredFlow, detected_type: str, fields: dict):
    env = fields.get("data_env") or fields.get("environment")
    if env and env.lower() in ("dev", "prd"):
        flow.environment = env.lower()
    ent = fields.get("enterprise_or_func_name")
    if ent and ent.upper() in ("AGTR", "CORP", "FOOD", "SPEC"):
        flow.selected_enterprise = ent.upper()


async def _handle_go_back(session: SessionState) -> dict:
    flow = session.structured_flow
    phase_order = [
        "q1_env", "q2_resource", "q2_enterprise",
        "q3_conditionals", "classification", "text_collection",
    ]
    current_idx = phase_order.index(flow.phase) if flow.phase in phase_order else 0

    if current_idx <= 0:
        return _present_q1_environment(session)

    prev_phase = phase_order[current_idx - 1]

    if flow.phase == "q2_resource":
        flow.selected_resource = None
    elif flow.phase == "q2_enterprise":
        flow.selected_resource = None
        flow.selected_enterprise = None
    elif flow.phase == "q3_conditionals":
        flow.selected_enterprise = None

    if prev_phase == "q1_env":
        flow.environment = None
        return _present_q1_environment(session)
    elif prev_phase == "q2_resource":
        flow.selected_resource = None
        return _present_q2_resources(session)
    elif prev_phase == "q2_enterprise":
        return _present_q2_enterprise(session)
    elif prev_phase == "q3_conditionals":
        flow.compute_q3_questions()
        return await _present_q3(session)
    elif prev_phase == "classification":
        return _present_classification(session)

    return _present_q1_environment(session)


def _resolve_resource_key(text: str) -> Optional[str]:
    text = text.strip().lower()
    if text in RESOURCE_OPTIONS:
        return text

    fuzzy_pairs = [
        ("source bucket", "s3_source"), ("source s3", "s3_source"),
        ("dataproduct bucket", "s3_dataproduct"), ("data product bucket", "s3_dataproduct"),
        ("data product", "s3_dataproduct"), ("dp bucket", "s3_dataproduct"),
        ("dataproduct", "s3_dataproduct"),
        ("scripts bucket", "s3_scripts"), ("script bucket", "s3_scripts"),
        ("engassets bucket", "s3_engassets"), ("engineering assets", "s3_engassets"),
        ("eng assets", "s3_engassets"), ("engassets", "s3_engassets"),
        ("raw source db", "glue_raw"), ("raw source", "glue_raw"),
        ("raw db", "glue_raw"),
        ("curated db", "glue_curated"),
        ("serving db", "glue_serving"),
        ("internal db", "glue_internal"),
        ("scripts", "s3_scripts"), ("script", "s3_scripts"),
        ("curated", "glue_curated"),
        ("serving", "glue_serving"),
        ("internal", "glue_internal"),
    ]
    for phrase, key in fuzzy_pairs:
        if phrase in text:
            return key

    short_exact = {"source": "s3_source", "raw": "glue_raw"}
    if text in short_exact:
        return short_exact[text]

    return None


def _build_resource_options() -> list:
    return [
        {"label": "🪣 Source Bucket (S3)", "value": "s3_source",
         "description": "Data ingestion from source systems → Lakehouse"},
        {"label": "🪣 DataProduct Bucket (S3)", "value": "s3_dataproduct",
         "description": "Transformed data → Compute"},
        {"label": "🪣 Scripts Bucket (S3)", "value": "s3_scripts",
         "description": "ETL scripts and code"},
        {"label": "🪣 EngAssets Bucket (S3)", "value": "s3_engassets",
         "description": "Engineering assets"},
        {"label": "📊 Raw Source DB (Glue)", "value": "glue_raw",
         "description": "Raw data ingestion layer → Lakehouse"},
        {"label": "📊 Curated DB (Glue)", "value": "glue_curated",
         "description": "Processed data → Compute"},
        {"label": "📊 Serving DB (Glue)", "value": "glue_serving",
         "description": "Analytics / serving layer → Compute"},
        {"label": "📊 Internal DB (Glue)", "value": "glue_internal",
         "description": "Internal processing / staging"},
    ]


def _derive_account_from_flow(flow: StructuredFlow, agent: AgentState):
    from app.agents.field_deriver import (
        _S3_SOURCE_ACCOUNT, _S3_DATAPRODUCT_ACCOUNT,
        _GLUE_LAKEHOUSE_DEV, _GLUE_LAKEHOUSE_PRD, _GLUE_COMPUTE,
    )

    config = flow.get_resource_config()
    env = flow.environment
    enterprise = (flow.selected_enterprise or "").lower()
    resource_type = config.get("resource_type")

    if resource_type == "s3":
        usage_type = config.get("auto_fields", {}).get("usage_type", "")
        if usage_type == "Source":
            acct = _S3_SOURCE_ACCOUNT.get(env)
            if acct:
                agent.collected_fields["aws_account_id"] = acct
        elif usage_type == "DataProduct":
            ent_map = _S3_DATAPRODUCT_ACCOUNT.get(enterprise)
            if ent_map:
                acct = ent_map.get(env)
                if acct:
                    agent.collected_fields["aws_account_id"] = acct
        elif usage_type in ("Scripts", "EngAssets"):
            if flow.account_placement == "lakehouse":
                acct = _S3_SOURCE_ACCOUNT.get(env)
                if acct:
                    agent.collected_fields["aws_account_id"] = acct
            elif flow.account_placement == "compute":
                ent_map = _S3_DATAPRODUCT_ACCOUNT.get(enterprise)
                if ent_map:
                    acct = ent_map.get(env)
                    if acct:
                        agent.collected_fields["aws_account_id"] = acct

    elif resource_type == "glue_db":
        data_layer = config.get("auto_fields", {}).get("data_layer", "")
        if data_layer in ("raw", "raw_serving"):
            acct = _GLUE_LAKEHOUSE_DEV if env == "dev" else _GLUE_LAKEHOUSE_PRD
            agent.collected_fields["aws_account_id"] = acct
        elif data_layer in ("curated", "serving"):
            ent_map = _GLUE_COMPUTE.get(enterprise)
            if ent_map:
                acct = ent_map.get(env)
                if acct:
                    agent.collected_fields["aws_account_id"] = acct
        elif data_layer == "internal":
            if flow.account_placement == "lakehouse":
                acct = _GLUE_LAKEHOUSE_DEV if env == "dev" else _GLUE_LAKEHOUSE_PRD
                agent.collected_fields["aws_account_id"] = acct
            elif flow.account_placement == "compute":
                ent_map = _GLUE_COMPUTE.get(enterprise)
                if ent_map:
                    acct = ent_map.get(env)
                    if acct:
                        agent.collected_fields["aws_account_id"] = acct


async def _parse_combined_input(flow, raw_text: str) -> dict:
    resource_descriptions = []
    for res_key in flow.selected_resources:
        config = RESOURCE_OPTIONS.get(res_key, {})
        label = config.get("label", res_key)
        rtype = config.get("resource_type", "s3")
        auto = config.get("auto_fields", {})

        needs = ["intake_id"]
        if rtype == "glue_db":
            construct = auto.get("data_construct", "")
            layer = auto.get("data_layer", "")
            if construct == "Source" or layer == "raw":
                needs.append("source_name")
            if construct == "DataProduct" or layer in ("curated", "serving"):
                needs.append("data_product_name")
            if layer == "serving" and flow.serving_purpose:
                needs.append(f"serving_purpose (already known: {flow.serving_purpose})")

        resource_descriptions.append(f"- {res_key} ({label}): needs {', '.join(needs)}")

    resources_text = "\n".join(resource_descriptions)

    prompt = f"""Parse the user's message into fields for each resource.

Resources to fill:
{resources_text}

Shared fields needed (for all Glue databases):
- data_privacy: PI, PCI, PHI, BCI, or NONE
- data_owner_email: email address
- data_owner_github_uname: GitHub username
- data_leader: leader ID or name

User message: {raw_text}

Return JSON with resource keys as top-level keys, plus "_shared" for shared fields.
Each resource key maps to a dict of field values.
Example:
{{
  "s3_source": {{"intake_id": "M0000789"}},
  "glue_raw": {{"intake_id": "M0000789", "source_name": "sa3"}},
  "_shared": {{"data_privacy": "PI", "data_owner_email": "john@example.com", "data_owner_github_uname": "johndoe", "data_leader": "KatiePorter"}}
}}

If multiple resources share the same intake_id, use the same ID.
If the user maps specific IDs to specific resources, follow their mapping.
Only return the JSON, nothing else."""

    try:
        result = await llm_client.extract_json(
            [{"role": "user", "content": prompt}], max_tokens=2048
        )
        logger.info(f"Parsed combined input: {list(result.keys())}")
        return result
    except Exception as e:
        logger.error(f"Failed to parse combined input: {e}")
        return _regex_parse_combined(flow, raw_text)


def _regex_parse_combined(flow, raw_text: str) -> dict:
    result = {}
    text_lower = raw_text.lower()

    intake_ids = re.findall(r"\b[MI]-?\d{4,10}\b", raw_text, re.IGNORECASE)

    source_match = re.search(r"source\s+(?:is\s+|name\s+)?[:\-]?\s*(\w+)", text_lower)
    source_name = source_match.group(1) if source_match else None

    product_match = re.search(
        r"(?:product|data\s*product)\s+(?:is\s+|name\s+)?[:\-]?\s*(\w+)", text_lower
    )
    product_name = product_match.group(1) if product_match else None

    privacy_match = re.search(r"\b(PI|PCI|PHI|BCI|SPI|NONE)\b", raw_text)
    privacy = privacy_match.group(1) if privacy_match else "NONE"

    email_match = re.search(r"[\w.+-]+@[\w.-]+\.\w+", raw_text)
    email = email_match.group(0) if email_match else None

    gh_match = re.search(r"github\s+(?:user(?:name)?\s+)?(\w+)", text_lower)
    gh_user = gh_match.group(1) if gh_match else None

    leader_match = re.search(r"leader\s+(?:is\s+)?(\w+)", text_lower)
    leader = leader_match.group(1) if leader_match else None

    id_idx = 0
    for res_key in flow.selected_resources:
        config = RESOURCE_OPTIONS.get(res_key, {})
        rtype = config.get("resource_type", "s3")
        auto = config.get("auto_fields", {})
        entry = {}

        if id_idx < len(intake_ids):
            entry["intake_id"] = intake_ids[id_idx]
            id_idx += 1

        if rtype == "glue_db":
            construct = auto.get("data_construct", "")
            layer = auto.get("data_layer", "")
            if (construct == "Source" or layer == "raw") and source_name:
                entry["source_name"] = source_name
            if (construct == "DataProduct" or layer in ("curated", "serving")) and product_name:
                entry["data_product_name"] = product_name

        result[res_key] = entry

    result["_shared"] = {
        "data_privacy": privacy,
        "data_owner_email": email,
        "data_owner_github_uname": gh_user,
        "data_leader": leader,
    }
    return result


def _generate_bucket_description(flow, res_key: str) -> str:
    config = RESOURCE_OPTIONS.get(res_key, {})
    usage = config.get("auto_fields", {}).get("usage_type", "data")
    enterprise = flow.selected_enterprise or ""
    subgroup = flow.subgroup or ""
    purpose_map = {
        "Source": "source data",
        "DataProduct": "data product",
        "Scripts": "ETL scripts and code",
        "EngAssets": "engineering assets",
    }
    purpose = purpose_map.get(usage, usage.lower())
    entity = f"{enterprise} {subgroup}".strip() if subgroup else enterprise
    return f"Stores {purpose} for {entity} subgroup"


def _generate_db_description(flow, res_key: str, agent) -> str:
    config = RESOURCE_OPTIONS.get(res_key, {})
    auto = config.get("auto_fields", {})
    layer = agent.collected_fields.get("data_layer", auto.get("data_layer", ""))
    enterprise = flow.selected_enterprise or ""
    subgroup = flow.subgroup or ""
    source = agent.collected_fields.get("source_name", "")
    product = agent.collected_fields.get("data_product_name", "")
    purpose = agent.collected_fields.get("purpose", flow.serving_purpose or "")
    entity = f"{enterprise} {subgroup}".strip() if subgroup else enterprise
    data_subject = source or product or "data"

    if purpose:
        return f"Stores {data_subject.capitalize()} {layer.capitalize()} Data Product for {entity} {purpose}"
    return f"Database for {data_subject} to {layer} patterns for {entity}"


def _show_multi_yaml_preview(session: SessionState, flow) -> dict:
    parts = []
    any_failed = False
    for i, entry in enumerate(flow.completed_resource_yamls, 1):
        if entry['yaml']:
            parts.append(
                f"### {i}. {entry['label']} ({entry['resource_type'].upper()})\n\n"
                f"```yaml\n{entry['yaml']}\n```"
            )
        else:
            any_failed = True
            fields_summary = "\n".join(f"  - {k}: {v}" for k, v in entry['fields'].items())
            parts.append(
                f"### {i}. {entry['label']} ({entry['resource_type'].upper()})\n\n"
                f"⚠️ **YAML generation failed** — the LLM service was unreachable.\n"
                f"Collected fields:\n{fields_summary}\n\n"
                f"You can **confirm** to retry generation, or **cancel** to start over."
            )

    combined = "\n\n---\n\n".join(parts)

    last = flow.completed_resource_yamls[-1]
    agent = session.start_new_resource()
    agent.resource_type = last["resource_type"]
    agent.collected_fields = last["fields"]
    agent.generated_yaml = last["yaml"] or ""
    agent.multi_preview_entries = list(flow.completed_resource_yamls)
    agent.phase = "awaiting_confirmation"

    session.structured_flow = None

    count = len(flow.completed_resource_yamls)
    status_msg = (
        f"Here are your **{count} resource configurations**. "
        f"Please review and **confirm**, **edit**, or **cancel**."
    )
    if any_failed:
        status_msg += "\n\n⚠️ Some YAML generation failed due to connectivity issues. Confirm to retry."

    return build_response(
        f"{status_msg}\n\n{combined}",
        resource_type=last["resource_type"],
        resource_status="awaiting_confirmation",
        generated_yaml=last["yaml"] or "",
        needs_confirmation=True,
    )
