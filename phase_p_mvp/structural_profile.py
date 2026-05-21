"""
structural_profile.py

Core engine for "Structural Embeddings" (Phase Q).
Projects code metrics into a data-driven latent space discovered via PCA.

UPDATED (Phase Q+1 Prep):
- Implements Mahalanobis Distance for Structural Anomaly Scoring (Risk).
- Uses full Precision Matrix (Inverse Covariance) to weight rare structures.
- Guards against zero-division and model version drift.
- Renames 'Modernity' to 'Paradigm' for accuracy.
"""
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class StructuralProfile:
    # Latent Dimensions (3D Visualization)
    complexity: float = 0.0  # PC1
    resilience: float = 0.0  # PC2
    paradigm: float = 0.0    # PC3 (was Modernity)
    
    # Risk / Uncertainty
    structural_anomaly: float = 0.0    # Original d^2 (Geometry)
    structural_anomaly_z: float = 0.0  # Robust Z-Score (Probability/Risk)
    entropy: float = 0.0             # Archetypal Ambiguity (Legacy but useful)
    
    # Context
    ambiguity: str = "unknown"
    nearest: list = field(default_factory=list)
    interpretation: str = ""

    @property
    def vector(self) -> List[float]:
        return [self.complexity, self.resilience, self.paradigm]


# =============================================================================
# MAHALANOBIS PROJECTOR (The "Navigator")
# =============================================================================

class MahalanobisProjector:
    """
    Projector that computes both Latent Coordinates (for human intuition)
    and Structural Anomaly Scores (for machine risk assessment).
    """
    
    def __init__(self, model_path: Path):
        raw = json.loads(model_path.read_text(encoding="utf-8"))
        
        # Version Check (Prevent Silent Corruption)
        if raw.get("version") != "1.1":
            print(f"WARNING: Structural Model Version Mismatch. Expected 1.1, got {raw.get('version')}")
            
        self.feature_names = raw["feature_names"]
        self.mean = raw["mean"]
        self.std = raw["std"]
        self.components = raw["components"]  # All PC vectors
        self.eigenvalues = raw["explained_variance"]
        self.precision_matrix = raw["precision_matrix"] # Inverse Covariance for Mahalanobis
        
        # Load Calibration Stats (Phase Q+1)
        try:
            calib_path = model_path.parent / "structural_calibration_stats.json"
            if calib_path.exists():
                calib = json.loads(calib_path.read_text(encoding="utf-8"))
                stats = calib["stats"]
                self.median_d2 = stats.get("median", 11.0) # Fallback to Theoretical
                self.mad_d2 = stats.get("mad", 4.7)        # Fallback to Theoretical
                print(f"Loaded Calibration Stats: Median={self.median_d2}, MAD={self.mad_d2}")
            else:
                self.median_d2 = 11.0
                self.mad_d2 = 4.7
                print("WARNING: Calibration stats not found. Using theoretical defaults.")
        except Exception as e:
            print(f"Error loading calibration stats: {e}")
            self.median_d2 = 11.0
            self.mad_d2 = 4.7
        
    def project(self, metrics: Dict[str, float]) -> Tuple[float, float, float, float, float]:
        """
        Projects to (PC1, PC2, PC3, Anomaly_d2, Anomaly_Z).
        Anomaly_Z is Robust Z-Score: (d2 - median) / MAD.
        """
        # 1. Align and Standardize
        vector = []
        for i, name in enumerate(self.feature_names):
            val = float(metrics.get(name, 0.0))
            if isinstance(metrics.get(name), bool):
                val = 1.0 if metrics[name] else 0.0
            
            # Guard against zero-division (though std should be > 0 from PCA)
            sigma = self.std[i]
            if sigma < 1e-9:
                sigma = 1.0 # Fallback safety
                
            z = (val - self.mean[i]) / sigma
            vector.append(z)
            
        # 2. Project to Top 3 (Visualization)
        # Using dot product with first 3 eigenvectors
        pc1 = sum(vector[j] * self.components[0][j] for j in range(len(vector)))
        pc2 = sum(vector[j] * self.components[1][j] for j in range(len(vector)))
        pc3 = sum(vector[j] * self.components[2][j] for j in range(len(vector)))
        
        # 3. Compute Structural Anomaly (Mahalanobis Distance)
        # d^2 = z^T * Precision * z
        # vector is already z-standardized (x-u)/sigma.
        # Wait - covariance was computed on X_std. So precision applies to X_std.
        anomaly_sq = 0.0
        for r in range(len(vector)):
            row_sum = 0.0
            for c in range(len(vector)):
                row_sum += vector[c] * self.precision_matrix[r][c]
            anomaly_sq += vector[r] * row_sum
            
        # 4. Compute Robust Z-Score
        # Guard against zero MAD (though unlikely given audit)
        denom = self.mad_d2 if self.mad_d2 > 1e-6 else 1.0
        anomaly_z = (anomaly_sq - self.median_d2) / denom
            
        return pc1, pc2, pc3, anomaly_sq, anomaly_z

# Singleton instance
try:
    PROJECTOR = MahalanobisProjector(Path(__file__).parent / "structural_pca_model.json")
except Exception as e:
    print(f"Warning: Could not load Structural PCA Model: {e}")
    PROJECTOR = None


# =============================================================================
# LOGIC
# =============================================================================

def compute_profile(metrics: Dict, archetype_scores: Optional[Dict[str, float]] = None, corpus: Optional[List[dict]] = None) -> StructuralProfile:
    """
    Compute structural profile using purely data-driven projection AND probabilistic entropy.
    """
    # 1. Latent Projection & Anomaly Scoring
    if PROJECTOR:
        pc1, pc2, pc3, anomaly, anomaly_z = PROJECTOR.project(metrics)
    else:
        pc1, pc2, pc3, anomaly, anomaly_z = 0.0, 0.0, 0.0, 0.0, 0.0
        
    # 2. Entropy / Ambiguity (Legacy but useful for "Hybrid" reasoning)
    if archetype_scores:
        # Normalize scores to probability distribution for entropy
        total_score = sum(archetype_scores.values())
        if total_score > 0:
            probs = [s / total_score for s in archetype_scores.values()]
            H = -sum(p * math.log2(p) for p in probs if p > 0)
        else:
            H = 0.0
    else:
        H = 0.0
        
    # Classification based on Anomaly & Entropy
    ambiguity = "clear"
    # Use Robust Z-Score for novelty (z > 2.0 is "Unusual", z > 3.0 is "Anomaly")
    # We set threshold at 2.0 for "structurally_novel" classification
    if anomaly_z > 2.0:
        ambiguity = "structurally_novel"
    elif H > 1.2:
        ambiguity = "ambiguous"
    elif H < 0.5:
        ambiguity = "stereotypical"
        
    profile = StructuralProfile(
        complexity=round(pc1, 4),
        resilience=round(pc2, 4),
        paradigm=round(pc3, 4),
        structural_anomaly=round(anomaly, 4),
        structural_anomaly_z=round(anomaly_z, 4),
        entropy=round(H, 4),
        ambiguity=ambiguity
    )

    # 3. Nearest neighbors in Latent Space (using simple Euclidean on Top 3)
    # Note: Could use full Mahalanobis distance for neighbors too, but visual space is often enough.
    if corpus and PROJECTOR:
        # Project corpus on the fly (inefficient but fine for MVP)
        neighbors = []
        for point in corpus:
            p_metrics = point["metrics"]
            p_pc1, p_pc2, p_pc3, _, _ = PROJECTOR.project(p_metrics)
            dist = math.sqrt((pc1 - p_pc1)**2 + (pc2 - p_pc2)**2 + (pc3 - p_pc3)**2)
            neighbors.append({
                "method": point["method"],
                "repo": point["repo"],
                "distance": round(dist, 4)
            })
        
        # Sort by distance
        neighbors.sort(key=lambda x: x["distance"])
        profile.nearest = neighbors[:3]
        
    # 4. Generate Interpretation
    profile.interpretation = generate_interpretation(profile)
    
    return profile


def generate_interpretation(p: StructuralProfile) -> str:
    """
    Generate natural language description of the structural location.
    """
    traits = []
    
    # Complexity (PC1)
    if p.complexity > 2.0: traits.append("Highly complex, deeply nested logic")
    elif p.complexity > 0.5: traits.append("Moderately complex logic")
    elif p.complexity < -2.0: traits.append("Trivial, atomic logic")
    elif p.complexity < -0.5: traits.append("Simple, flat logic")
    
    # Resilience (PC2)
    if p.resilience > 2.0: traits.append("heavily defensive (robust error handling)")
    elif p.resilience > 0.5: traits.append("guarded (some error handling)")
    elif p.resilience < -2.0: traits.append("fragile (optimistic path only)")
    elif p.resilience < -0.5: traits.append("optimistic (little error handling)")
    
    # Paradigm (PC3)
    # Positive = Imperative (Loops), Negative = Modern (Types) -- based on PCA loadings
    if p.paradigm > 1.5: traits.append("classic imperative style")
    elif p.paradigm < -1.5: traits.append("modern/typed paradigm")
    
    base_desc = "; ".join(traits)
    
    if p.structural_anomaly > 20.0:
        return f"STRUCTURAL ANOMALY (d2={p.structural_anomaly:.1f}): {base_desc}. This structure is statistically rare."
        
    return base_desc


def format_profile(profile: StructuralProfile, method_name: str = "Method") -> str:
    """Format profile for CLI output."""
    lines = []
    lines.append(f"Structural Profile for '{method_name}':")
    lines.append(f"    Latent Vector: [{profile.complexity:>6.2f}, {profile.resilience:>6.2f}, {profile.paradigm:>6.2f}]")
    lines.append(f"      (Complexity, Resilience, Paradigm)")
    lines.append(f"    Anomaly Score: d^2={profile.structural_anomaly:>5.1f} | Z={profile.structural_anomaly_z:>5.2f} (Robust)")
    lines.append(f"    Ambiguity: {profile.ambiguity} (H={profile.entropy:.2f})")
    lines.append(f"    Interpretation: {profile.interpretation}")
    
    if profile.nearest:
        lines.append("\n    Nearest Neighbors (Structural Space):")
        for n in profile.nearest:
            lines.append(f"      - {n['repo']}::{n['method']} (dist={n['distance']:.2f})")
            
    return "\n".join(lines)


# =============================================================================
# TEST
# =============================================================================
if __name__ == "__main__":
    # Load some mock data to test projection
    print("Testing Mahalanobis Projector...")
    
    m1 = {
        "unique_caller_files": 30, # High complexity
        "max_nesting_depth": 5,
        "try_block_ratio": 0.5,    # High resilience
        "exception_types_count": 3,
        "type_hint_ratio": 0.8,    # Modern (negative PC3)
        "loop_count": 0
    }
    
    p1 = compute_profile(m1)
    print(format_profile(p1, "Complex Mock"))
    
    m2 = {
        "unique_caller_files": 1, # Low complexity
        "max_nesting_depth": 0,
        "try_block_ratio": 0.0,   # Low resilience
        "type_hint_ratio": 0.0,   # Old style?
        "loop_count": 5           # Imperative
    }
    p2 = compute_profile(m2)
    print("\n" + format_profile(p2, "Simple Imperative Mock"))
    
    # Weird mock (Anomaly)
    m3 = {
        "unique_caller_files": 100, # Extreme
        "try_block_ratio": 0.0,
        "type_hint_ratio": 0.0
    }
    p3 = compute_profile(m3, {}, [])
    print("\n" + format_profile(p3, "Anomaly Mock"))
