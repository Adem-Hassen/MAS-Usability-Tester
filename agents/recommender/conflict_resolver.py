#agents/recommender/conflict_resolver.py


from __future__ import annotations

import json
import uuid
from typing import Optional

from config.settings import settings
from tools.rate_limiter import groq_chat_completion
from core.state import GraphState
from schemas.patch_schema import (
    PatchProposal, PatchType,
    ConflictRecord, NegotiationRound, NegotiationSession,
    ResolvedPatch, UnifiedPatchSet,
)
from prompts.recommender_prompts import (
    CONFLICT_DETECTION_SYSTEM, CONFLICT_DETECTION_USER,
    NEGOTIATION_ARGUMENT_SYSTEM, NEGOTIATION_ARGUMENT_USER,
    MEDIATOR_SYSTEM, MEDIATOR_USER,
)
from monitoring.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# LangGraph node entry point
# ---------------------------------------------------------------------------

def conflict_resolver_node(state: GraphState) -> dict:
    """
    LangGraph node. Receives all patch_proposals, resolves conflicts,
    returns unified_patch_set.
    """
    proposals: list[PatchProposal] = state.get("patch_proposals", [])
    logger.info("conflict_resolver.start", total_proposals=len(proposals))

    if not proposals:
        logger.warning("conflict_resolver.no_proposals")
        return {
            "unified_patch_set": UnifiedPatchSet(
                patches=[],
                conflicts_detected=0,
                conflicts_resolved=0,
                negotiation_sessions=[],
                unresolved_conflicts=[],
            )
        }

    # Filter out fallback/zero-confidence stubs before conflict detection
    viable = [p for p in proposals if p.confidence > 0.0]
    skipped = len(proposals) - len(viable)
    if skipped:
        logger.info("conflict_resolver.skipped_fallbacks", count=skipped)

    if not viable:
        return {
            "unified_patch_set": UnifiedPatchSet(
                patches=[],
                conflicts_detected=0,
                conflicts_resolved=0,
            )
        }

    # Step 1: Detect conflicts
    conflicts = _detect_conflicts(viable)
    logger.info("conflict_resolver.conflicts_detected", count=len(conflicts))

    # Step 2: Resolve each conflict via LLM negotiation
    sessions:        list[NegotiationSession] = []
    winner_map:      dict[str, str]            = {}  # patch_id → winning patch_id
    merged_snippets: dict[str, str]            = {}  # patch_id → merged after_snippet
    unresolved:      list[ConflictRecord]      = []

    proposal_map = {p.patch_id: p for p in viable}

    for conflict in conflicts:
        session, resolution = _resolve_conflict(
            conflict, proposal_map, sessions_so_far=sessions
        )
        sessions.append(session)

        if session.final_resolution == "chose_a":
            winner_map[conflict.patch_id_b] = conflict.patch_id_a
        elif session.final_resolution == "chose_b":
            winner_map[conflict.patch_id_a] = conflict.patch_id_b
        elif session.final_resolution == "merged":
            # Both patches are "superseded" — we'll build a merged ResolvedPatch
            winner_map[conflict.patch_id_a] = f"merged_{conflict.conflict_id}"
            winner_map[conflict.patch_id_b] = f"merged_{conflict.conflict_id}"
            merged_snippets[f"merged_{conflict.conflict_id}"] = session.merged_snippet or ""
        else:  # unresolved
            # Keep the higher-confidence patch
            pa = proposal_map.get(conflict.patch_id_a)
            pb = proposal_map.get(conflict.patch_id_b)
            if pa and pb:
                if pa.confidence >= pb.confidence:
                    winner_map[conflict.patch_id_b] = conflict.patch_id_a
                else:
                    winner_map[conflict.patch_id_a] = conflict.patch_id_b
            unresolved.append(conflict)

        logger.info(
            "conflict_resolver.conflict_resolved",
            conflict_id=conflict.conflict_id,
            resolution=session.final_resolution,
            rounds=len(session.rounds),
        )

    # Step 3: Build the final resolved patch list
    resolved_patches = _build_resolved_patches(
        viable, conflicts, winner_map, merged_snippets, sessions
    )

    conflicts_resolved = len(conflicts) - len(unresolved)

    unified = UnifiedPatchSet(
        patches=resolved_patches,
        conflicts_detected=len(conflicts),
        conflicts_resolved=conflicts_resolved,
        negotiation_sessions=sessions,
        unresolved_conflicts=unresolved,
    )

    logger.info(
        "conflict_resolver.complete",
        resolved_patches=len(resolved_patches),
        conflicts_detected=len(conflicts),
        conflicts_resolved=conflicts_resolved,
        unresolved=len(unresolved),
    )

    return {"unified_patch_set": unified}


# ---------------------------------------------------------------------------
# Step 1: Conflict detection
# ---------------------------------------------------------------------------

def _detect_conflicts(proposals: list[PatchProposal]) -> list[ConflictRecord]:
    """
    Call the LLM to identify conflicts between patch proposals.
    Falls back to simple selector-overlap heuristic on LLM failure.
    """
    patches_json = json.dumps(
        [p.model_dump() for p in proposals], indent=2, default=str
    )

    user = CONFLICT_DETECTION_USER.format(patches_json=patches_json)

    raw, error = _call_resolver_llm(
        system=CONFLICT_DETECTION_SYSTEM,
        user=user,
        task="conflict_detection",
    )

    if error:
        logger.warning("conflict_resolver.detection_llm_error", error=error)
        return _heuristic_conflict_detection(proposals)

    try:
        data = json.loads(raw)
        # Unwrap {"conflicts": [...]} container
        if isinstance(data, dict):
            data = next(iter(data.values()))
        if not isinstance(data, list):
            return _heuristic_conflict_detection(proposals)

        conflicts = []
        for i, item in enumerate(data):
            conflicts.append(ConflictRecord(
                conflict_id=item.get("conflict_id", f"conflict_{i+1}"),
                patch_id_a=item["patch_id_a"],
                patch_id_b=item["patch_id_b"],
                target_element=item.get("target_element", "unknown"),
                conflict_description=item.get("conflict_description", ""),
                conflict_severity=item.get("conflict_severity", "medium"),
            ))
        return conflicts

    except Exception as e:
        logger.warning("conflict_resolver.detection_parse_error", error=str(e))
        return _heuristic_conflict_detection(proposals)


def _heuristic_conflict_detection(proposals: list[PatchProposal]) -> list[ConflictRecord]:
    """
    Fallback: two patches conflict if they share the same target_element
    AND the same patch-type category.

    Cross-type patches (e.g. one HTML + one CSS on the same element) are
    orthogonal and NOT conflicting — per the architecture doc and the LLM
    conflict detection prompt which explicitly lists these as non-conflicts.
    """
    _CSS_CATS = {"css_rule", "css_class"}
    _JS_CATS  = {"js_snippet"}

    def _type_category(pt: str) -> str:
        if pt in _CSS_CATS:
            return "css"
        if pt in _JS_CATS:
            return "js"
        return "html"

    conflicts = []
    # Group by (target_element, type_category) — only same-category can conflict
    seen: dict[tuple[str, str], list[PatchProposal]] = {}
    for p in proposals:
        key = (p.target_element, _type_category(str(p.patch_type)))
        seen.setdefault(key, []).append(p)

    conflict_idx = 1
    for (selector, _cat), group in seen.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                conflicts.append(ConflictRecord(
                    conflict_id=f"conflict_{conflict_idx}",
                    patch_id_a=group[i].patch_id,
                    patch_id_b=group[j].patch_id,
                    target_element=selector,
                    conflict_description=(
                        f"Both patches target '{selector}' with same type category "
                        f"'{_cat}' — potential conflict detected by heuristic fallback."
                    ),
                    conflict_severity="medium",
                ))
                conflict_idx += 1

    return conflicts


# ---------------------------------------------------------------------------
# Step 2: Conflict resolution via negotiation
# ---------------------------------------------------------------------------

def _resolve_conflict(
    conflict: ConflictRecord,
    proposal_map: dict[str, PatchProposal],
    sessions_so_far: list[NegotiationSession],
) -> tuple[NegotiationSession, str]:
    """
    Run up to settings.conflict_max_negotiation_rounds negotiation rounds for one conflict.
    Returns (NegotiationSession, final_resolution_string).
    """
    pa = proposal_map.get(conflict.patch_id_a)
    pb = proposal_map.get(conflict.patch_id_b)

    session_id = f"session_{conflict.conflict_id}_{uuid.uuid4().hex[:4]}"
    rounds: list[NegotiationRound] = []

    if pa is None or pb is None:
        # One of the patches was already eliminated by a previous resolution
        surviving = pa or pb
        resolution = "chose_a" if pa else "chose_b"
        return NegotiationSession(
            session_id=session_id,
            conflict=conflict,
            rounds=[],
            final_resolution=resolution,
            winning_patch_id=surviving.patch_id if surviving else None,
            merged_snippet=None,
        ), resolution

    final_resolution = "unresolved"
    winning_id:    Optional[str] = None
    merged_snippet: Optional[str] = None

    for round_num in range(1, settings.conflict_max_negotiation_rounds + 1):
        # Each agent argues for its patch
        arg_a = _get_agent_argument(
            agent_id=pa.recommender_id,
            patch=pa,
            competing_patch=pb,
            conflict=conflict,
        )
        arg_b = _get_agent_argument(
            agent_id=pb.recommender_id,
            patch=pb,
            competing_patch=pa,
            conflict=conflict,
        )

        # Mediator assesses and decides
        previous_rounds_json = json.dumps(
            [r.model_dump() for r in rounds], indent=2, default=str
        )
        mediator_result = _get_mediator_decision(
            conflict=conflict,
            pa=pa, pb=pb,
            arg_a=arg_a, arg_b=arg_b,
            previous_rounds=previous_rounds_json,
        )

        resolution_reached = mediator_result.get("resolution") in (
            "chose_a", "chose_b", "merged"
        )
        proposed_resolution = mediator_result.get("resolution", "unresolved")

        nround = NegotiationRound(
            round_number=round_num,
            conflict_id=conflict.conflict_id,
            agent_a_argument=arg_a.get("argument", ""),
            agent_b_argument=arg_b.get("argument", ""),
            mediator_assessment=mediator_result.get("resolution_rationale", ""),
            resolution_reached=resolution_reached,
            proposed_resolution=proposed_resolution if resolution_reached else None,
        )
        rounds.append(nround)

        if resolution_reached:
            final_resolution = proposed_resolution
            winning_id    = mediator_result.get("winning_patch_id")
            merged_snippet = mediator_result.get("merged_snippet")
            break

    # Last-resort tie-break: keep higher-confidence patch
    if final_resolution == "unresolved":
        if pa.confidence >= pb.confidence:
            final_resolution = "chose_a"
            winning_id = pa.patch_id
        else:
            final_resolution = "chose_b"
            winning_id = pb.patch_id
        logger.warning(
            "conflict_resolver.tiebreak",
            conflict_id=conflict.conflict_id,
            winner=winning_id,
        )

    return NegotiationSession(
        session_id=session_id,
        conflict=conflict,
        rounds=rounds,
        final_resolution=final_resolution,
        winning_patch_id=winning_id,
        merged_snippet=merged_snippet,
    ), final_resolution


def _get_agent_argument(
    agent_id: str,
    patch: PatchProposal,
    competing_patch: PatchProposal,
    conflict: ConflictRecord,
) -> dict:
    """Ask one agent to argue for its patch. Returns parsed dict."""
    system = NEGOTIATION_ARGUMENT_SYSTEM.format(
        agent_id=agent_id,
        patch_id=patch.patch_id,
    )
    user = NEGOTIATION_ARGUMENT_USER.format(
        target_element=conflict.target_element,
        conflict_description=conflict.conflict_description,
        your_patch_json=json.dumps(patch.model_dump(), indent=2, default=str),
        competing_patch_json=json.dumps(competing_patch.model_dump(), indent=2, default=str),
    )
    raw, error = _call_resolver_llm(system, user, task="agent_argument")
    if error or not raw:
        return {
            "agent_id": agent_id,
            "patch_id": patch.patch_id,
            "argument": f"[LLM error — defaulting to confidence={patch.confidence:.2f}]",
            "acknowledged_weaknesses": "",
            "proposed_compromise": None,
        }
    try:
        return json.loads(raw)
    except Exception:
        return {"argument": raw[:500], "patch_id": patch.patch_id}


def _get_mediator_decision(
    conflict: ConflictRecord,
    pa: PatchProposal,
    pb: PatchProposal,
    arg_a: dict,
    arg_b: dict,
    previous_rounds: str,
) -> dict:
    """Ask the mediator to resolve the conflict. Returns parsed dict."""
    user = MEDIATOR_USER.format(
        conflict_json=json.dumps(conflict.model_dump(), indent=2, default=str),
        patch_a_json=json.dumps(pa.model_dump(), indent=2, default=str),
        argument_a=arg_a.get("argument", ""),
        patch_b_json=json.dumps(pb.model_dump(), indent=2, default=str),
        argument_b=arg_b.get("argument", ""),
        previous_rounds=previous_rounds,
    )
    raw, error = _call_resolver_llm(MEDIATOR_SYSTEM, user, task="mediation")
    if error or not raw:
        return {"resolution": "unresolved", "winning_patch_id": None}
    try:
        return json.loads(raw)
    except Exception:
        return {"resolution": "unresolved", "winning_patch_id": None}


# ---------------------------------------------------------------------------
# Step 3: Build resolved patches
# ---------------------------------------------------------------------------

def _build_resolved_patches(
    proposals: list[PatchProposal],
    conflicts: list[ConflictRecord],
    winner_map: dict[str, str],
    merged_snippets: dict[str, str],
    sessions: list[NegotiationSession],
) -> list[ResolvedPatch]:
    """
    Produce the final list of ResolvedPatch objects.

    Rules:
      - Non-conflicting patches: pass straight through (0 rounds, no negotiation).
      - Winning patches from chose_a / chose_b: preserved, rounds = actual rounds used.
      - Merged patches: one new ResolvedPatch per merged pair with the combined snippet.
      - Loser patches: dropped entirely (not included in output).
    """
    conflicted_ids: set[str] = set()
    for c in conflicts:
        conflicted_ids.add(c.patch_id_a)
        conflicted_ids.add(c.patch_id_b)

    # Build session lookup by conflict_id for round count
    rounds_by_conflict: dict[str, int] = {}
    session_by_conflict: dict[str, NegotiationSession] = {}
    for s in sessions:
        rounds_by_conflict[s.conflict.conflict_id] = len(s.rounds)
        session_by_conflict[s.conflict.conflict_id] = s

    # Map proposal → conflict it was involved in
    conflict_of: dict[str, ConflictRecord] = {}
    for c in conflicts:
        conflict_of[c.patch_id_a] = c
        conflict_of[c.patch_id_b] = c

    resolved: list[ResolvedPatch] = []
    processed_merged: set[str] = set()  # avoid duplicate merged patches
    proposal_map = {p.patch_id: p for p in proposals}

    for p in proposals:
        if p.patch_id not in conflicted_ids:
            # No conflict — straight-through resolved patch
            resolved.append(_proposal_to_resolved(p, negotiation_rounds=0))
            continue

        override = winner_map.get(p.patch_id)

        # Case: this patch was a loser (override points to a different patch_id)
        if override and override != p.patch_id and not override.startswith("merged_"):
            continue  # dropped

        # Case: merged patch
        if override and override.startswith("merged_"):
            if override in processed_merged:
                continue
            processed_merged.add(override)
            conflict = conflict_of[p.patch_id]
            other_id = (
                conflict.patch_id_b if p.patch_id == conflict.patch_id_a else conflict.patch_id_a
            )
            other_p = proposal_map.get(other_id)
            snippet = merged_snippets.get(override, p.after_snippet)
            session = session_by_conflict.get(conflict.conflict_id)
            rationale = (
                session.rounds[-1].mediator_assessment
                if session and session.rounds
                else "Merged by conflict resolver."
            )
            resolved.append(ResolvedPatch(
                resolved_patch_id=f"resolved_{override}",
                source_patch_ids=[p.patch_id, other_id],
                cluster_ids=list({p.cluster_id, other_p.cluster_id} if other_p else {p.cluster_id}),
                patch_type=p.patch_type,
                target_element=p.target_element,
                description=f"Merged fix: {p.description}",
                before_snippet=p.before_snippet,
                after_snippet=snippet,
                css_snippet=p.css_snippet,
                js_snippet=p.js_snippet,
                negotiation_rounds=rounds_by_conflict.get(conflict.conflict_id, 0),
                resolution_rationale=rationale,
                wcag_reference=p.wcag_reference,
                confidence=min(
                    p.confidence,
                    other_p.confidence if other_p else p.confidence,
                ),
            ))
            continue

        # Case: this patch is the winner (override == None or override == self)
        conflict = conflict_of.get(p.patch_id)
        rounds   = rounds_by_conflict.get(conflict.conflict_id, 0) if conflict else 0
        session  = session_by_conflict.get(conflict.conflict_id) if conflict else None
        rationale = (
            session.rounds[-1].mediator_assessment
            if session and session.rounds
            else "Chosen by conflict resolver (no negotiation needed)."
        )
        rp = _proposal_to_resolved(p, negotiation_rounds=rounds)
        # Override resolution_rationale with mediator note
        resolved.append(ResolvedPatch(
            **{**rp.model_dump(), "resolution_rationale": rationale}
        ))

    # Sort by cluster priority (approximated by cluster_id string order)
    resolved.sort(key=lambda r: r.cluster_ids[0] if r.cluster_ids else "")
    return resolved


def _proposal_to_resolved(
    proposal: PatchProposal,
    negotiation_rounds: int,
) -> ResolvedPatch:
    """Convert a PatchProposal directly to a ResolvedPatch (no conflict involved)."""
    return ResolvedPatch(
        resolved_patch_id=f"resolved_{proposal.patch_id}",
        source_patch_ids=[proposal.patch_id],
        cluster_ids=[proposal.cluster_id],
        patch_type=proposal.patch_type,
        target_element=proposal.target_element,
        description=proposal.description,
        before_snippet=proposal.before_snippet,
        after_snippet=proposal.after_snippet,
        css_snippet=proposal.css_snippet,
        js_snippet=proposal.js_snippet,
        negotiation_rounds=negotiation_rounds,
        resolution_rationale=(
            "No conflict — patch accepted as-is."
            if negotiation_rounds == 0
            else "Conflict resolved without negotiation."
        ),
        wcag_reference=proposal.wcag_reference,
        confidence=proposal.confidence,
    )


# ---------------------------------------------------------------------------
# LLM helper
# ---------------------------------------------------------------------------

def _call_resolver_llm(
    system: str,
    user:   str,
    task:   str,
) -> tuple[str, Optional[str]]:
    """Groq-aware LLM call with rate limiting."""
    return groq_chat_completion(
        api_key     = settings.resolver_api_key,
        model       = settings.resolver_llm_model,
        messages    = [{"role": "system", "content": system},
                       {"role": "user",   "content": user}],
        temperature = settings.resolver_temperature,
        max_tokens  = getattr(settings, 'resolver_max_tokens', settings.llm_max_output_tokens),
        task        = task,
    )