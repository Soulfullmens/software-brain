"""
Recursive Controller - Hypothesis-driven reasoning.

Flow:
1. Generate hypotheses from the question
2. Plan initial exploration based on hypothesis search hints
3. Explore chunks, feed evidence to belief state
4. Map beliefs to hypotheses (support/contradict/resolve gaps)
5. Generate discriminating probes to distinguish hypotheses
6. If gaps remain → plan follow-up based on GAPS + call-site targets
7. Stop only when: gaps resolved, hypotheses disambiguated, or search exhausted
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from controller.trace import log
from controller.belief_state import BeliefState, BeliefStatus
from controller.hypothesis import (
    Hypothesis, HypothesisStatus,
    generate_hypotheses,
    map_beliefs_to_hypotheses,
    get_exploration_targets,
    generate_discriminating_probes,
    evaluate_probes_against_beliefs,
    generate_callsite_targets
)
from controller.planner import load_chunk_metadata
from controller.planner import plan_initial_chunks
from controller.planner import plan_followup_chunks
from controller.planner import score_chunk_relevance
from controller.planner import CHUNK_METADATA
from workers.worker import process_chunk
from index.chunk_index import create_chunks


def _hypotheses_resolved(hypotheses):
    """Check if all hypotheses are resolved (confirmed or rejected)."""
    for h in hypotheses:
        if h.status in (HypothesisStatus.PENDING, HypothesisStatus.INVESTIGATING):
            return False
    return True


def _hypotheses_disambiguated(hypotheses):
    """
    Check if hypotheses are disambiguated.
    True when: confidence spread between top and bottom >= 0.3,
    or only one hypothesis is SUPPORTED/CONFIRMED.
    """
    active = [h for h in hypotheses 
              if h.status in (HypothesisStatus.SUPPORTED, HypothesisStatus.CONFIRMED)]
    
    if len(active) <= 1:
        return True
    
    confidences = [h.confidence for h in active]
    spread = max(confidences) - min(confidences)
    return spread >= 0.3


def _has_unresolved_gaps(hypotheses):
    """Check if any active hypothesis still has unresolved gaps."""
    for h in hypotheses:
        if h.status not in (HypothesisStatus.REJECTED,):
            if h.missing_evidence:
                return True
    return False


def _select_chunks_by_gaps(hypotheses, explored, max_chunks=3):
    """
    Select chunks to explore based on hypothesis GAPS + call-site targets.
    """
    targets = get_exploration_targets(hypotheses)
    if not targets:
        return []

    scored = []
    for chunk_id, meta in CHUNK_METADATA.items():
        if chunk_id in explored:
            continue
        score = score_chunk_relevance(chunk_id, targets)
        if score > 0:
            scored.append((chunk_id, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [c for c, s in scored][:max_chunks]


def _select_chunks_by_callsites(hypotheses, explored, max_chunks=3):
    """
    Find chunks containing specific call sites.
    Uses substring matching: 'freeze' matches '_emergency_freeze', 'manual_freeze', etc.
    """
    callsite_terms = generate_callsite_targets(hypotheses)
    if not callsite_terms:
        return []
    
    callsite_lower = [t.lower().strip("(). ") for t in callsite_terms]
    
    scored = []
    for chunk_id, meta in CHUNK_METADATA.items():
        if chunk_id in explored:
            continue
        
        content_index = meta.get("content_index", {})
        all_content = set()
        for key in ["keywords", "entities", "enums", "concepts", "verbs"]:
            all_content.update(t.lower() for t in content_index.get(key, []))
        
        # Score by substring matching: 'freeze' matches 'manual_freeze'
        hits = 0
        matched_terms = set()
        for term in callsite_lower:
            # Exact match
            if term in all_content:
                hits += 1.0
                matched_terms.add(term)
                continue
            # Substring match: term appears IN any content item, or vice versa
            for item in all_content:
                if len(term) >= 4 and term in item:
                    hits += 0.7
                    matched_terms.add(term)
                    break
                elif len(item) >= 4 and item in term:
                    hits += 0.3
                    matched_terms.add(term)
                    break
        
        if hits > 0:
            scored.append((chunk_id, hits))
    
    scored.sort(key=lambda x: x[1], reverse=True)
    return [c for c, s in scored][:max_chunks]


def controller(question: str, max_depth: int = 5):
    """
    Hypothesis-driven recursive controller.
    
    Recursion stops ONLY when:
    1. All gaps are resolved, OR
    2. Hypotheses are disambiguated, OR
    3. No new chunks to explore (search exhausted), OR
    4. Max depth reached (safety limit)
    """
    log({"type": "START", "question": question})

    # Step 1: Build index
    chunks = create_chunks()
    load_chunk_metadata(chunks)
    total_chunks = len(chunks)
    log({"type": "INDEX_CREATED", "num_chunks": total_chunks})

    # Step 2: Generate hypotheses BEFORE exploring
    hypotheses = generate_hypotheses(question)
    log({"type": "HYPOTHESES_GENERATED",
         "count": len(hypotheses),
         "hypotheses": [h.to_dict() for h in hypotheses]})

    # Step 3: Initialize belief state
    belief_state = BeliefState()

    # Step 4: Plan initial exploration from hypothesis search hints
    all_hints = set()
    for h in hypotheses:
        all_hints.update(h.search_hints)
    initial_chunks = plan_initial_chunks(question, max_chunks=5)
    log({"type": "INITIAL_PLAN",
         "planned_chunks": initial_chunks,
         "search_hints": list(all_hints),
         "skipped_chunks": total_chunks - len(initial_chunks)})

    # Step 5: Recursive exploration driven by hypothesis gaps
    explored = set()
    depth = 0
    to_explore = initial_chunks.copy()
    probes = []

    while to_explore and depth < max_depth:
        # Check if hypotheses are fully resolved AND disambiguated
        if _hypotheses_resolved(hypotheses) and _hypotheses_disambiguated(hypotheses):
            log({"type": "HYPOTHESES_RESOLVED_AND_DISAMBIGUATED", "depth": depth})
            break

        log({"type": "RECURSION_LEVEL", "depth": depth,
             "chunks_to_explore": len(to_explore),
             "overall_confidence": belief_state.get_overall_confidence(),
             "num_beliefs": len(belief_state.beliefs),
             "hypotheses": [h.to_dict() for h in hypotheses]})

        # Explore chunks
        for chunk_id in to_explore:
            if chunk_id in explored:
                continue

            log({"type": "DELEGATE", "chunk_id": chunk_id, "depth": depth})
            explored.add(chunk_id)

            result = process_chunk(chunk_id, question)

            # Feed claims to belief state
            claims = result.get("claims", [])
            for claim in claims:
                belief_state.add_evidence(chunk_id, claim)

            log({"type": "WORKER_RESULT", "chunk_id": chunk_id,
                 "num_claims": len(claims),
                 "extraction_method": result.get("extraction_method", "unknown")})

        # Map beliefs to hypotheses
        map_beliefs_to_hypotheses(hypotheses, belief_state.beliefs)

        # Generate and evaluate discriminating probes
        if depth >= 1 and not _hypotheses_disambiguated(hypotheses):
            probes = generate_discriminating_probes(hypotheses)
            if probes:
                evaluate_probes_against_beliefs(probes, belief_state.beliefs, hypotheses)
                
                resolved_probes = sum(1 for p in probes if p.found)
                log({"type": "DISCRIMINATION_PROBES",
                     "total_probes": len(probes),
                     "resolved": resolved_probes,
                     "probes": [{"desc": p.description, "found": p.found, 
                                "supports": p.supports_hypothesis[:50] if p.supports_hypothesis else "neutral"} 
                               for p in probes]})

        log({"type": "HYPOTHESIS_UPDATE",
             "hypotheses": [h.to_dict() for h in hypotheses],
             "disambiguated": _hypotheses_disambiguated(hypotheses)})

        # Decide next: keep searching if gaps remain or hypotheses need disambiguation
        if not _hypotheses_resolved(hypotheses) or not _hypotheses_disambiguated(hypotheses):
            # Strategy 1: Gap-driven exploration
            gap_chunks = _select_chunks_by_gaps(hypotheses, explored, max_chunks=3)
            
            # Strategy 2: Call-site targeted search
            callsite_chunks = _select_chunks_by_callsites(hypotheses, explored, max_chunks=2)
            
            # Merge, dedup, prefer callsite chunks
            to_explore = []
            seen = set()
            for c in callsite_chunks + gap_chunks:
                if c not in seen:
                    to_explore.append(c)
                    seen.add(c)
            to_explore = to_explore[:5]  # Cap at 5 per round
            
            if to_explore:
                log({"type": "CONTINUED_EXPLORATION",
                     "new_chunks": to_explore,
                     "from_gaps": [c for c in gap_chunks if c in to_explore],
                     "from_callsites": [c for c in callsite_chunks if c in to_explore],
                     "remaining_gaps": sum(len(h.missing_evidence) for h in hypotheses),
                     "reason": "gaps_unresolved" if _has_unresolved_gaps(hypotheses) else "disambiguation_needed"})
            else:
                log({"type": "SEARCH_EXHAUSTED",
                     "reason": "no_unexplored_chunks_match_gaps_or_callsites",
                     "total_explored": len(explored),
                     "remaining_gaps": sum(len(h.missing_evidence) for h in hypotheses)})
                break
        else:
            to_explore = []

        depth += 1

    # Step 6: Synthesize answer from hypotheses + beliefs
    synthesis = belief_state.synthesize_answer()

    hypothesis_summary = []
    for h in hypotheses:
        hypothesis_summary.append({
            "statement": h.statement,
            "status": h.status.value,
            "confidence": h.confidence,
            "supporting_count": len(h.supporting),
            "contradicting_count": len(h.contradicting),
            "unresolved_gaps": h.missing_evidence,
            "absence_penalties": h.expected_but_missing
        })

    response = {
        "hypotheses": hypothesis_summary,
        "beliefs": synthesis,
        "used_chunks": list(explored),
        "total_chunks": total_chunks,
        "chunks_explored": len(explored),
        "chunks_skipped": total_chunks - len(explored),
        "recursion_depth": depth,
        "discriminating_probes": len(probes),
        "probes_resolved": sum(1 for p in probes if p.found) if probes else 0
    }

    log({"type": "FINAL_RESPONSE", **response})

    # Print readable summary
    print(f"\n{'='*60}")
    print(f"  EXPLORATION STATS")
    print(f"{'='*60}")
    print(f"  Total chunks: {total_chunks}")
    print(f"  Explored: {len(explored)} ({100*len(explored)/total_chunks:.1f}%)")
    print(f"  Skipped: {total_chunks - len(explored)}")
    print(f"  Recursion depth: {depth}")
    if probes:
        print(f"  Discriminating probes: {len(probes)} ({sum(1 for p in probes if p.found)} resolved)")

    print(f"\n{'='*60}")
    print(f"  HYPOTHESES")
    print(f"{'='*60}")
    for h in hypotheses:
        icon = {"confirmed": "✓", "supported": "~", "rejected": "✗",
                "investigating": "?", "pending": "○"}.get(h.status.value, "?")
        penalty_str = f" [-{h.expected_but_missing} absence]" if h.expected_but_missing else ""
        print(f"  [{icon}] ({h.confidence:.2f}) {h.statement}{penalty_str}")
        if h.missing_evidence:
            for gap in h.missing_evidence:
                print(f"      MISSING: {gap}")
        if h.supporting:
            print(f"      {len(h.supporting)} supporting, {len(h.contradicting)} contradicting")

    print(f"\n{'='*60}")
    print(f"  BELIEF STATE")
    print(f"{'='*60}")
    print(f"  Total beliefs: {len(belief_state.beliefs)}")
    print(f"  Overall confidence: {belief_state.get_overall_confidence():.3f}")
    top = belief_state.get_top_beliefs(5)
    for b in top:
        icon = {"confirmed": "✓", "supported": "~", "conflicted": "!",
                "unconfirmed": "?"}.get(b.status.value, "?")
        print(f"  [{icon}] ({b.confidence:.2f}) {b.statement[:70]}")

    return response
