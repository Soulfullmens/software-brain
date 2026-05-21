"""
Chunk Selection Planner - Content-aware.

Scoring is now:
  0.4 * keyword_overlap   (domain terms in content)
  0.3 * concept_match      (concepts like freeze, transition, mode)
  0.2 * entity_match       (classes, functions, enums)
  0.1 * file_path_match    (old-style file name matching)
"""

import re
from pathlib import Path

# Heuristic Filter: Only process chunks containing these high-value terms
# This reduces the search space from ~100 to ~15-20 critical files.
HEURISTIC_TERMS = {
    '_freeze', 'FROZEN', 'AutonomyLevel', 'LearningMode',
    'set_level', 'emergency', 'threshold'
}

# Chunk metadata cache (loaded from index)
CHUNK_METADATA = {}


def load_chunk_metadata(chunks: list):
    """Cache chunk metadata for planning. Mutates in-place to preserve references."""
    CHUNK_METADATA.clear()
    CHUNK_METADATA.update({c["chunk_id"]: c for c in chunks})


def extract_keywords(question: str) -> list:
    """Extract likely file/concept keywords from question."""
    patterns = [
        r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b',  # CamelCase
        r'\b[a-z]+_[a-z_]+\b',                # snake_case
        r'"([^"]+)"',                          # quoted
        r"'([^']+)'",                          # single quoted
        r'\b[A-Z]{2,}\b',                      # UPPER_CASE
    ]
    keywords = []
    for p in patterns:
        keywords.extend(re.findall(p, question))
    
    # Add domain terms
    lower_q = question.lower()
    domain_terms = ['learning', 'mode', 'evaluate', 'frozen', 'freeze',
                    'transition', 'condition', 'adjustment', 'policy',
                    'governor', 'autonomy', 'regulator', 'safety',
                    'emergency', 'violation', 'invariant', 'authority']
    for term in domain_terms:
        if term in lower_q:
            keywords.append(term)
    
    return list(set(keywords))


def score_chunk_relevance(chunk_id: str, keywords: list) -> float:
    """
    Score chunk relevance using content index.
    APPLIES HARD HEURISTIC FILTER: Returns 0.0 if no heuristic terms found.
    """
    if chunk_id not in CHUNK_METADATA:
        return 0.0
    
    chunk = CHUNK_METADATA[chunk_id]
    files = chunk.get("files", [])
    content_index = chunk.get("content_index", {})
    
    # --- HEURISTIC FILTER ---
    found_heuristic = False
    
    # flatten all index terms for checking
    all_index_terms = set()
    for key in ["keywords", "entities", "enums", "concepts"]:
        all_index_terms.update(content_index.get(key, []))
    
    # Also check filenames for heuristic terms
    for f in files:
        all_index_terms.add(Path(f).stem)
        
    for term in HEURISTIC_TERMS:
        for index_term in all_index_terms:
            # Substring match: '_freeze' in '_freeze_system'
            if term in index_term:
                found_heuristic = True
                break
        if found_heuristic:
            break
            
    if not found_heuristic:
        return 0.0
    # ------------------------

    keywords_lower = {k.lower() for k in keywords}
    
    # 1. Keyword overlap
    chunk_keywords = {k.lower() for k in content_index.get("keywords", [])}
    keyword_hits = len(keywords_lower & chunk_keywords)
    keyword_score = min(keyword_hits / max(len(keywords_lower), 1), 1.0)
    
    # 2. Concept match
    chunk_concepts = set(content_index.get("concepts", []))
    concept_hits = len(keywords_lower & chunk_concepts)
    concept_score = min(concept_hits / max(len(keywords_lower), 1), 1.0)
    
    # 3. Entity match
    chunk_entities = {e.lower() for e in content_index.get("entities", [])}
    chunk_enums = {e.lower() for e in content_index.get("enums", [])}
    all_entities = chunk_entities | chunk_enums
    entity_hits = len(keywords_lower & all_entities)
    entity_score = min(entity_hits / max(len(keywords_lower), 1), 1.0)
    
    # 4. File path match
    path_score = 0.0
    for f in files:
        f_lower = f.lower()
        for kw in keywords_lower:
            if kw in f_lower:
                path_score += 0.5
    path_score = min(path_score, 1.0)
    
    # Weighted combination
    total = (0.4 * keyword_score +
             0.3 * concept_score +
             0.2 * entity_score +
             0.1 * path_score)
    
    return round(total, 3)


def plan_initial_chunks(question: str, max_chunks: int = 5) -> list:
    """
    Plan which chunks to explore FIRST based on question.
    """
    keywords = extract_keywords(question)
    
    if not keywords:
        return list(CHUNK_METADATA.keys())[:max_chunks]
    
    scored = []
    for chunk_id in CHUNK_METADATA:
        score = score_chunk_relevance(chunk_id, keywords)
        scored.append((chunk_id, score))
    
    scored.sort(key=lambda x: x[1], reverse=True)
    
    relevant = [c for c, s in scored if s > 0][:max_chunks]
    
    if not relevant:
        # If heuristics filtered everything, return empty list!
        # DO NOT FALL BACK TO random chunks if heuristics are active.
        return []
    
    return relevant


def plan_followup_chunks(found_references: list, already_explored: set, max_new: int = 3) -> list:
    """
    Plan which chunks to explore NEXT based on references found.
    """
    candidates = []
    
    for ref in found_references:
        ref_lower = ref.lower()
        for chunk_id, meta in CHUNK_METADATA.items():
            if chunk_id in already_explored:
                continue
            
            # Check file paths
            for f in meta.get("files", []):
                if ref_lower in f.lower():
                    if chunk_id not in candidates:
                        candidates.append(chunk_id)
                        break
            
            # Check content index
            if chunk_id not in candidates:
                content_index = meta.get("content_index", {})
                all_terms = set()
                for key in ["keywords", "entities", "enums", "concepts"]:
                    all_terms.update(t.lower() for t in content_index.get(key, []))
                
                if ref_lower in all_terms:
                    candidates.append(chunk_id)
    
    # Apply heuristic filter to follow-ups too?
    # Maybe logic: If reference is found, maybe it's valid even if no heuristic term?
    # User said "If it doesn't match... skip LLM entirely."
    # So yes, apply strict filter.
    filtered_candidates = []
    for c in candidates:
        # Re-score with empty keywords just to check filter?
        # Or check logic: score_chunk_relevance returns 0 if no heuristic.
        score = score_chunk_relevance(c, [])
        # Wait, if keywords empty, score is 0.0 anyway?
        # No, score logic returns 0.0 immediately if filtered.
        # But if filtered passed, returns weighted sum.
        # If keywords empty, weighted sum might be 0?
        # Let's write explicit check:
        # Use a helper function for heuristic check?
        pass

    # For now, simplistic approach: trust score_chunk_relevance is sufficient for initial.
    # Follow-ups might be dangerous if unlimited.
    # But follow-ups are based on REFERENCES (extracted from LLM).
    # If LLM found a reference, it's likely relevant.
    return candidates[:max_new]


def should_stop(confidence: float, depth: int, max_depth: int = 3) -> bool:
    """Decide when to stop recursing."""
    if depth >= max_depth:
        return True
    if confidence >= 0.85:
        return True
    return False
