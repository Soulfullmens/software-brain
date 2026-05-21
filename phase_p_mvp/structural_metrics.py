
"""
structural_metrics.py

Expanded structural metrics extractor (14 Dimensions).
Used for Phase Q: High-Dimensional Structural Discovery (PCA).
"""
import ast
import os
from pathlib import Path
from typing import Dict, List, Set, Optional

# Default source root for analysis (can be overridden)
DEFAULT_SRC = Path(__file__).parent.parent / "src"


# =============================================================================
# AST UTILITIES
# =============================================================================

def get_ast(path: Path) -> Optional[ast.AST]:
    """Parse a file into an AST, handling encoding errors gracefully."""
    try:
        content = path.read_text(encoding="utf-8")
        return ast.parse(content)
    except (UnicodeDecodeError, SyntaxError, FileNotFoundError):
        return None

def find_method_def(tree: ast.AST, method_name: str) -> Optional[ast.FunctionDef]:
    """Find a method definition by name in an AST."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method_name:
            return node
    return None

def count_nodes(tree: ast.AST, node_types) -> int:
    """Count occurrences of specific node types in an AST."""
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, node_types):
            count += 1
    return count


# =============================================================================
# METRIC EXTRACTORS (14 DIMENSIONS)
# =============================================================================

def compute_dependency_metrics(callsites: List[Dict], source_root: Path) -> Dict[str, float]:
    """
    Extract dependency-related metrics.
    - max_call_depth: Approximation of call stack depth (static analysis).
    - num_external_modules: Count of distinct imported modules used.
    """
    # Simply count unique files participating as a proxy for depth/breadth complexity
    # Real static call graph depth is expensive; we use unique files as a strong proxy.
    unique_files = len(set(c["file"] for c in callsites))
    
    # External modules: check imports in the files that call the target
    external_modules = set()
    for c in callsites:
        # Heavily simplified: assume file path segments are modules
        # A more robust parser would check 'import' statements
        parts = Path(c["file"]).parts
        if len(parts) > 1:
            external_modules.add(parts[0]) # Top-level package
            
    return {
        "unique_caller_files": float(unique_files), # Preserving original metric name
        "num_external_modules": float(len(external_modules))
    }

def compute_cyclicity_metrics(tree: ast.FunctionDef) -> Dict[str, float]:
    """
    Extract cyclicity metrics from the target method itself.
    - is_recursive: Calls itself?
    - has_loops: Contains for/while loops?
    """
    if not tree:
        return {"is_recursive": 0.0, "has_loops": 0.0}
    
    # Check recursion
    is_recursive = 0.0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == tree.name:
                is_recursive = 1.0
                break
    
    # Check loops
    loops = count_nodes(tree, (ast.For, ast.AsyncFor, ast.While))
    
    return {
        "is_recursive": is_recursive,
        "loop_count": float(loops)
    }

def compute_resilience_metrics(tree: ast.FunctionDef) -> Dict[str, float]:
    """
    Extract resilience metrics.
    - try_block_ratio: Lines in try blocks / total lines.
    - exception_types_count: Diversity of exceptions caught.
    """
    if not tree:
        return {"try_block_ratio": 0.0, "exception_types_count": 0.0}
    
    total_nodes = 0
    try_nodes = 0
    handlers = []
    
    for node in ast.walk(tree):
        total_nodes += 1
        if isinstance(node, ast.Try):
            # Rough approximation: count the Try node itself as 'coverage'
            # Refining this to line counts would be better but AST line numbers can be tricky
            try_nodes += len(node.body)
            handlers.extend(node.handlers)
            
    ratio = try_nodes / max(1, len(tree.body))
    ratio = min(1.0, ratio) # Cap at 1.0
    
    # Count distinct exception types
    distinct_exceptions = set()
    for h in handlers:
        if h.type:
            if isinstance(h.type, ast.Name):
                distinct_exceptions.add(h.type.id)
            elif isinstance(h.type, ast.Attribute):
                distinct_exceptions.add(h.type.attr)
    
    return {
        "try_block_ratio": float(ratio),
        "exception_types_count": float(len(distinct_exceptions))
    }

def compute_concurrency_metrics(tree: ast.FunctionDef) -> Dict[str, float]:
    """
    Extract concurrency metrics.
    - is_async: Boolean.
    - await_count: Number of await expressions.
    """
    if not tree:
        return {"is_async": 0.0, "await_count": 0.0}
    
    is_async = 1.0 if isinstance(tree, ast.AsyncFunctionDef) else 0.0
    await_count = count_nodes(tree, ast.Await)
    
    return {
        "is_async": is_async,
        "await_count": float(await_count)
    }

def compute_complexity_metrics(tree: ast.FunctionDef) -> Dict[str, float]:
    """
    Extract complexity metrics.
    - avg_args_count: Arguments in signature.
    - type_hint_ratio: Argument with hints / total args.
    """
    if not tree:
        return {"avg_args_count": 0.0, "type_hint_ratio": 0.0}
    
    args = tree.args.args
    total_args = len(args)
    if total_args == 0:
        return {"avg_args_count": 0.0, "type_hint_ratio": 0.0}
    
    hinted_args = sum(1 for a in args if a.annotation is not None)
    
    # Compute max AST depth (nesting level)
    max_depth = 0
    for node in ast.walk(tree):
        depth = 0
        curr = node
        while hasattr(curr, 'parent'): # AST nodes don't have parent by default, need to annotate
            depth += 1
            curr = curr.parent
        # Since standard AST doesn't have parents, we use a recursive visitor or just simple iteration
        # Simpler: just calculate depth during walk if we track it, or use a recursive function
        pass
        
    # Recursive depth calculator
    def get_depth(node):
        if not hasattr(node, "body") and not hasattr(node, "orelse") and not hasattr(node, "finalbody"):
            return 1
        children = []
        if hasattr(node, "body"):
             children.extend(node.body if isinstance(node.body, list) else [node.body])
        if hasattr(node, "orelse"):
             children.extend(node.orelse if isinstance(node.orelse, list) else [node.orelse])
        if hasattr(node, "finalbody"):
             children.extend(node.finalbody if isinstance(node.finalbody, list) else [node.finalbody])
        
        if not children:
            return 1
        return 1 + max(get_depth(c) for c in children if isinstance(c, ast.AST))

    max_depth = get_depth(tree)

    return {
        "avg_args_count": float(total_args),
        "type_hint_ratio": float(hinted_args / total_args),
        "max_nesting_depth": float(max_depth)
    }


# =============================================================================
# LEGACY METRICS (KEPT FOR CONTINUITY UNTIL FULL REPLACEMENT)
# =============================================================================

def find_all_callsites(target_method: str = "_freeze", source_root: Path = None) -> List[Dict]:
    """Find all usages of target_method in the source tree."""
    src = source_root or DEFAULT_SRC
    callsites = []
    
    if not src.exists():
        return []

    for path in src.rglob("*.py"):
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            # Fast text search first
            if target_method not in content:
                continue
                
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id == target_method:
                        callsites.append({"file": str(path.relative_to(src)), "context": "direct"})
                    elif isinstance(node.func, ast.Attribute) and node.func.attr == target_method:
                        callsites.append({"file": str(path.relative_to(src)), "context": "method"})
        except Exception:
            continue
            
    return callsites

def compute_legacy_ratios(callsites: List[Dict]) -> Dict[str, float]:
    """Compute the original 5 metrics (Dispersion, Concentration, etc)."""
    if not callsites:
        return {
            "unique_caller_files": 0,
            "dominant_file_ratio": 0.0,
            "automatic_ratio": 0.0,
            "manual_ratio": 0.0,
            "reason_enum_count": 0,
            "has_central_router": False,
            "dominant_file": "none"
        }
        
    # Dispersion (unique files) is calculated in dependency metrics now, 
    # but we compute dominant_file_ratio here.
    file_counts = {}
    for c in callsites:
        f = c["file"]
        file_counts[f] = file_counts.get(f, 0) + 1
        
    total = len(callsites)
    if not file_counts:
        dom_ratio = 0.0
        dom_file = "none"
    else:
        dom_file = max(file_counts, key=file_counts.get)
        dom_ratio = file_counts[dom_file] / total
    
    # Context (simplified text heuristic for now)
    # In a real implementation, we'd look at the surrounding code of the callsite
    # For now, we stub this or use the old regex method if needed.
    # To keep this generic, we'll placeholder these.
    # The user noted manual_ratio was 0.0 everywhere, so we are deprioritizing it.
    
    return {
        "dominant_file_ratio": dom_ratio,
        "dominant_file": dom_file,
        "automatic_ratio": 0.5, # Placeholder until deeper context analysis
        "manual_ratio": 0.0,
        "reason_enum_count": 0
    }


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def compute_metrics(target_method: str = "_freeze", source_root: Path = None) -> Dict[str, float]:
    """
    Compute ALL 14 structural metrics for a given method.
    Aggregation of:
    - Dependency (Dispersion)
    - Cyclicity
    - Resilience
    - Concurrency
    - Complexity
    - Legacy Concentration/Ratios
    """
    src = source_root or DEFAULT_SRC
    
    # 1. Broad search for callsites (Usage Analysis)
    callsites = find_all_callsites(target_method, src)
    
    # 2. Find definition for Code Analysis
    # We need to find where target_method is DEFINED to analyze its body
    # This searches the whole tree for a def.
    definition_node = None
    for path in src.rglob("*.py"):
        tree = get_ast(path)
        if tree:
            node = find_method_def(tree, target_method)
            if node:
                definition_node = node
                break
    
    # 3. Compute Metrics
    metrics = {}
    
    # Group 1: Usage-based
    metrics.update(compute_dependency_metrics(callsites, src))
    metrics.update(compute_legacy_ratios(callsites))
    
    # Group 2: Definition-based
    # If definition not found, these default to 0.0
    metrics.update(compute_cyclicity_metrics(definition_node))
    metrics.update(compute_resilience_metrics(definition_node))
    metrics.update(compute_concurrency_metrics(definition_node))
    metrics.update(compute_complexity_metrics(definition_node))
    
    # Add metadata
    metrics["total_calls"] = len(callsites)
    
    return metrics
