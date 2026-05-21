"""
Phase 13: Decision Traceability Verification

Proves that:
1. Every proposal has a DecisionTrace
2. Trace explains WHY (Heuristics, Factors, Rejections)
3. Execution Log links back to the Trace (Decision ID)
"""

import pytest
from src.system.bootstrap import boot_agent
from src.system.intent import IntentContext
from src.cognition.belief_state import ContradictionRef

@pytest.fixture
def temp_brain_dir(tmp_path):
    path = tmp_path / "brain_data"
    path.mkdir()
    yield path

def test_decision_trace_and_audit_link(temp_brain_dir):
    # 1. Boot
    agent = boot_agent(temp_brain_dir, "Tracer")
    
    # 2. Manipulate State to force a specific decision
    # Case: Blocking Contradiction -> "resolve_contradiction"
    c_ref = ContradictionRef(
        id="c1",
        belief_a="b1",
        belief_b="b2",
        urgency=0.8,
        blocking=True
    )
    agent.belief_state.add_contradiction(c_ref)
    
    # 3. Planner Propose
    proposal = agent.planner.propose(agent.belief_state)
    assert proposal is not None
    assert proposal.action.id == "resolve_contradiction"
    assert proposal.action.target == "b1"
    
    # 4. Verify Trace
    trace = proposal.trace
    assert trace is not None
    assert trace.id is not None
    assert trace.match_heuristic == "resolve_contradiction"
    assert "contradiction_check" in trace.active_heuristics
    
    # Factors should list the contradiction
    assert any(f.type == "contradiction" and "c1" in f.id for f in trace.considered_factors)
    
    # 5. Execute
    ctx = IntentContext.create_agent_intent("Trace Test")
    result = agent.executor.execute(proposal, context=ctx)
    assert result is not None
    
    # 6. Verify Audit Link
    # Audit log is in memory (list) and on disk
    entries = agent.executor.audit_log.entries
    last_entry = entries[-1]
    
    assert last_entry.action_id == "resolve_contradiction"
    assert last_entry.outcome == "success"
    # THE LINK:
    assert last_entry.decision_id == trace.id
    
    print(f"[SUCCESS] Decision {trace.id} -> Action {last_entry.action_id} -> Audit Linked")

def test_trace_rejection_logic(temp_brain_dir):
    # Case: High Coherence, No Predictions -> "generate_prediction"
    agent = boot_agent(temp_brain_dir, "Tracer2")
    agent.belief_state.coherence_score = 1.0
    
    proposal = agent.planner.propose(agent.belief_state)
    assert proposal.action.id == "generate_prediction"
    
    trace = proposal.trace
    assert trace.match_heuristic == "generate_prediction"
    
    # Rationale: Should show that other heuristics were rejected
    assert "low_coherence" in trace.rejected_alternatives
    assert "resolve_contradiction" in trace.rejected_alternatives
    # "gather_evidence" might be in rejected or skipped depending on logic flow (nested)
    # My implementation appends to rejected if check fails.
    
    assert "resolve_contradiction" in trace.rejected_alternatives
    
    print("[SUCCESS] Trace correctly recorded rejected alternatives.")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
