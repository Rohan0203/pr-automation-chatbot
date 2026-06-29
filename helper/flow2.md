session_resolve
Finds existing chat thread or creates new one.
State: thread_id=t-101, pending=[], completed=[], blocked=[].
message_ingest
Stores user message in history.
State: turn_index=1, history now has this user message.
intent_router
Classifies as new supported resource request because S3 and Glue are supported.
Routes to resource_batch_planner.
resource_batch_planner
Creates two work items:
r1 = S3
r2 = Glue DB
State: pending=[r1, r2].
resource_scheduler
Selects pending resources for this turn: [r1, r2].
Routes each through resource graph.
resource_intent_confirm
Confirms resource intents:
r1: create S3 bucket
r2: create Glue DB
context_bind
Loads scoped context docs only for each resource:
S3 gets S3 docs
Glue gets Glue docs
field_extract
Extracts user-provided fields:
both resources get env=dev, enterprise=AGTR.
many fields still missing.
field_derive
Derives what can be derived using rules:
account id may be derived from env + enterprise
naming prefixes may be derived
Derived fields are marked editable.
field_confirmation
System shows proposal:
“I understood env=dev, enterprise=AGTR, derived account=... Is this correct?”
User can confirm or edit.
ConfirmDecision
If user says “edit account to X”, it loops back to field_confirmation.
If user says “yes”, proceed to completeness check.
completeness_check
Checks required fields:
S3 still missing: usage_type, subgroup
Glue still missing: data_layer, source_name
Routes to context_option_builder.
context_option_builder
Builds guided options:
enterprise AGTR -> subgroup options [A, B, C, D]
data_layer options [raw, curated, serving]
batched_missing_fields_planner
Creates one grouped ask:
For S3: usage_type, subgroup (with options)
For Glue: data_layer, source_name
response_aggregator
Builds one response with sections:
Completed: none
Pending asks: grouped S3 + Glue asks
Blocked: none
wait_for_next_user_turn
Saves checkpoint and waits.
message_ingest -> intent_router
This is an answer/update turn, so route to resource_scheduler.
resource_scheduler
Runs r1 and r2 again through resource flow.
field_extract + field_derive + field_confirmation
New values extracted and derived fields refreshed if needed, then confirmed.
completeness_check
Now both may be complete.
mark_resource_collected
Moves each complete resource from pending to completed.
State: pending=[], completed=[r1, r2].
response_aggregator
Returns collection-complete summary.
wait_for_next_user_turn
Checkpoint saved.
User says: “Create Databricks cluster.”
intent_router marks unsupported.
Goes to out_of_scope_handler.
Response says: “Databricks is out of scope for this app.”
Then wait_for_next_user_turn.
Suppose required non-derivable field source_name is repeatedly missing.
After retry threshold, batched_missing_fields_planner routes to blocked_incomplete_handler.
Resource r2 becomes blocked:
status=blocked_incomplete
status_reason=missing_required_fields
added to blocked_resource_ids.
response_aggregator shows blocked section clearly.
resume_later_handler
User intentionally pauses normal progress (“I’ll continue tomorrow”).
State is checkpointed as paused, not blocked.
resume_blocked_resource
User chooses to recover a blocked resource.
Moves resource from blocked back to pending and routes to scheduler.
 
 