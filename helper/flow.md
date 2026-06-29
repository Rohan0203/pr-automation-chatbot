Start
Purpose: Entry point for one turn execution.
Does: Initializes runtime context for this request lifecycle.
Output: Control goes to session_resolve.
session_resolve
Purpose: Attach request to the correct user session/thread.
Reads: user identity, session id, thread id, persisted checkpoint.
Does: Loads existing state or creates a new state object if none exists.
Writes: session metadata such as last_seen, session_version.
Output: Normalized conversation state for downstream nodes.
message_ingest
Purpose: Persist the latest user input into conversation history.
Reads: current user message payload.
Does: Appends message with timestamp, role, and correlation id.
Writes: message_history, turn_index increment.
Output: Updated state with latest turn data.
intent_router
Purpose: Decide what this turn represents.
Reads: latest message text, current resource statuses, pending asks, supported resource catalog.
Does: Classifies into new request, unsupported request, answer/edit/action flow.
Output: Route decision to resource_batch_planner, out_of_scope_handler, or resource_scheduler.
resource_batch_planner
Purpose: Split supported multi-resource request into independent work items.
Reads: routed intent and parsed resource intents.
Does: Creates one ResourceWorkItem per resource request.
Writes: resource_queue and pending_resource_ids.
Output: Queue ready for scheduling.
out_of_scope_handler
Purpose: Handle unsupported resource requests safely and clearly.
Reads: requested resource type and supported catalog.
Does: Generates explicit out-of-scope response with guidance.
Writes: response payload for user and audit event.
Output: Response path to wait_for_next_user_turn.
resource_scheduler
Purpose: Decide which pending resources should run in this turn.
Reads: pending_resource_ids, blocked_resource_ids, dropped/completed statuses, priority policy.
Does: Selects schedulable items and skips blocked/dropped/completed.
Writes: execution batch list for this turn.
Output: run resource graph or direct response_aggregator if nothing pending.
run resource graph per pending resource
Purpose: Execute per-resource pipeline independently.
Reads: each selected ResourceWorkItem.
Does: Runs resource_intent_confirm through completeness logic for each item.
Writes: item-level state updates and per-resource outcomes.
Output: Updated resource work items for aggregation.
resource_intent_confirm
Purpose: Validate resource type and requested operation.
Reads: resource_type, operation, context hints.
Does: Confirms or normalizes resource intent, rejects ambiguous intent if needed.
Writes: normalized resource intent fields.
Output: resource-specific validated intent.
context_bind
Purpose: Bind only allowed context documents for this resource and node.
Reads: context registry, resource_type, node policy.
Does: Loads minimal scoped context, not global context.
Writes: ContextBinding metadata for traceability.
Output: context slice for extraction/derivation.
field_extract
Purpose: Extract fields explicitly provided by user in this turn.
Reads: latest user message plus prior known fields.
Does: Parses values and maps to canonical schema keys.
Writes: extracted_fields and tentative updates in final_fields.
Output: extracted field set for derivation and confirmation.
field_derive
Purpose: Deterministically derive fields from known rules and context.
Reads: extracted fields, context maps, naming conventions.
Does: Computes derivable values and tags them as editable.
Writes: derived_fields and DerivationAudit entries.
Output: enriched proposed field set.
field_confirmation
Purpose: Keep final control with user before accepting values.
Reads: extracted plus derived field proposal.
Does: Presents proposal and edit affordance to user.
Writes: confirmation packet and editable candidate set.
Output: waits for confirm decision.
user confirms values? decision
Purpose: Branch based on user confirmation response.
Reads: confirm or edit action from user.
Does: Routes Yes to completeness_check, No to field_confirmation loop.
Writes: on edit, patched values in editable_fields/final_fields.
Output: confirmed field set or edited loop.
completeness_check
Purpose: Determine if required fields are complete.
Reads: final_fields, required schema, derivability metadata.
Does: Computes missing_fields and missing_fields_non_derivable.
Writes: completeness status on the resource item.
Output: mark_resource_collected or context_option_builder.
mark_resource_collected
Purpose: Mark one resource as collection-complete for this phase.
Reads: completeness result.
Does: Sets status completed and removes item from pending list.
Writes: completed_resource_ids and final accepted payload.
Output: per-resource completion result.
context_option_builder
Purpose: Build next-turn guided options from context relationships.
Reads: current field values and option maps such as enterprise to sub-enterprise.
Does: Produces constrained options for unresolved fields.
Writes: suggested_options_by_field.
Output: enriched ask inputs for batched planner.
batched_missing_fields_planner
Purpose: Build one grouped ask across all unresolved resources.
Reads: all pending resource missing fields plus option suggestions.
Does: Generates delta-only asks and avoids repeating answered fields.
Writes: BatchedAskPacket with grouped prompts and option lists.
Output: response_aggregator or blocked_incomplete_handler on retry threshold.
blocked_incomplete_handler
Purpose: Handle unresolved required non-derivable fields after retry limit.
Reads: field_attempts, missing_fields_non_derivable, policy thresholds.
Does: Marks resource as blocked_incomplete with clear reason and resume metadata.
Writes: blocked_resource_ids, status_reason, blocked_at_turn, resume_token.
Output: blocked status included in aggregate response.
response_aggregator
Purpose: Create one user-visible response summarizing all resource states.
Reads: completed, pending, blocked, out-of-scope, and confirmation/action outputs.
Does: Builds structured response sections and available next actions.
Writes: normalized UI/API response payload.
Output: wait_for_next_user_turn.
wait_for_next_user_turn
Purpose: Persist checkpoint and idle until next user action.
Reads: current conversation and resource state snapshot.
Does: Commits transactional checkpoint to database.
Writes: durable checkpoint and session metadata.
Output: next branch based on user action.
provide now branch
Purpose: User continues immediately with missing details.
Does: Routes back to message_ingest in same sitting.
skip for now branch
Purpose: User intentionally postpones current asks temporarily.
Does: Leaves state intact and returns to message_ingest later.
drop resource branch
Purpose: User abandons one resource request.
Does: Marks resource dropped and removes from pending queue.
Output: returns to next message cycle.
resume later next sitting branch and resume_later_handler
Purpose: Pause normal in-progress work for next session without marking blocked.
Reads: current in-progress state.
Does: Saves pause marker such as paused_by_user and keeps unresolved delta.
Writes: persisted checkpoint for later continuation.
Output: resumes from message_ingest in a future sitting.
resume blocked resource branch and resume_blocked_resource
Purpose: Recover a resource specifically from blocked_incomplete state.
Reads: blocked resource id and resume token.
Does: Moves resource from blocked list back to pending while preserving prior accepted data.
Writes: blocked to pending transition and retry context.
Output: returns to resource_scheduler for re-processing.
resource flow done
Purpose: Logical end marker for one resource execution path.
Does: Signals completion of that resource in current scheduling cycle.
 
 