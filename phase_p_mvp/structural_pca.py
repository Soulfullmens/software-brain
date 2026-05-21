"""
structural_pca.py

Pure Python implementation of PCA (Principal Component Analysis).
Extracts latent structural dimensions from high-dimensional calibration data.

UPDATED (Phase Q+1 Prep):
- Computes FULL eigenvalue spectrum for diagnosis.
- Computes Precision Matrix (Inverse Covariance) for Mahalanobis Distance.
- Exports robust model for anomaly detection.
"""
import json
import math
import random
from pathlib import Path
from typing import List, Tuple, Dict

# =============================================================================
# LINEAR ALGEBRA UTILITIES (Pure Python)
# =============================================================================

Matrix = List[List[float]]
Vector = List[float]

def zeros(rows: int, cols: int) -> Matrix:
    return [[0.0] * cols for _ in range(rows)]

def matmul(A: Matrix, B: Matrix) -> Matrix:
    """Matrix multiplication A @ B."""
    rows_A = len(A)
    cols_A = len(A[0])
    rows_B = len(B)
    cols_B = len(B[0])
    
    if cols_A != rows_B:
        raise ValueError(f"Shape mismatch: ({rows_A}x{cols_A}) @ ({rows_B}x{cols_B})")
        
    C = zeros(rows_A, cols_B)
    for i in range(rows_A):
        for j in range(cols_B):
            sum_ = 0.0
            for k in range(cols_A):
                sum_ += A[i][k] * B[k][j]
            C[i][j] = sum_
    return C

def transpose(A: Matrix) -> Matrix:
    """Transpose matrix."""
    rows = len(A)
    cols = len(A[0])
    return [[A[i][j] for i in range(rows)] for j in range(cols)]

def dot(v1: Vector, v2: Vector) -> float:
    """Dot product."""
    return sum(x*y for x, y in zip(v1, v2))

def norm(v: Vector) -> float:
    """Euclidean norm."""
    return math.sqrt(sum(x*x for x in v))

def normalize_vector(v: Vector) -> Vector:
    """Unit vector."""
    n = norm(v)
    if n < 1e-9: return v
    return [x/n for x in v]

def outer_product(v1: Vector, v2: Vector) -> Matrix:
    """Outer product v1 @ v2.T."""
    return [[x*y for y in v2] for x in v1]

def sub_matrix(A: Matrix, B: Matrix) -> Matrix:
    """Matrix subtraction A - B."""
    return [[A[i][j] - B[i][j] for j in range(len(A[0]))] for i in range(len(A))]


# =============================================================================
# PCA ALGORITHM (POWER ITERATION)
# =============================================================================

def power_iteration(A: Matrix, num_simulations: int = 2000) -> Tuple[float, Vector]:
    """
    Find dominant eigenvalue and eigenvector of symmetric matrix A.
    """
    n = len(A)
    # Random initialization (deterministic seed for stability)
    random.seed(42)
    b_k = [random.random() for _ in range(n)]
    b_k = normalize_vector(b_k)
    
    for _ in range(num_simulations):
        # Calculate matrix-by-vector product Ab
        b_k1 = [dot(row, b_k) for row in A]
        
        # Normalize
        b_k1_norm = norm(b_k1)
        if b_k1_norm < 1e-9:
            break
            
        b_k = [x / b_k1_norm for x in b_k1]
        
    # Rayleigh quotient to find eigenvalue
    Ab = [dot(row, b_k) for row in A]
    eigenvalue = dot(b_k, Ab)
    
    return eigenvalue, b_k

def pca(X: Matrix) -> Dict:
    """
    Perform PCA on data matrix X.
    Computes ALL components to enable full spectral inversion.
    """
    n_samples = len(X)
    n_features = len(X[0])
    
    # 1. Standardization (Z-score)
    means = [sum(row[j] for row in X)/n_samples for j in range(n_features)]
    
    # Standard deviation
    stds = []
    for j in range(n_features):
        variance = sum((row[j] - means[j])**2 for row in X) / (n_samples - 1)
        stds.append(math.sqrt(variance) if variance > 1e-9 else 1.0)
        
    # Scale X
    X_std = zeros(n_samples, n_features)
    for i in range(n_samples):
        for j in range(n_features):
            val = (X[i][j] - means[j]) / stds[j]
            X_std[i][j] = val
            
    # 2. Covariance Matrix
    X_T = transpose(X_std)
    C = matmul(X_T, X_std)
    for i in range(n_features):
        for j in range(n_features):
            C[i][j] /= (n_samples - 1)
            
    # 3. Eigendecomposition (Full Spectrum)
    eigenvalues = []
    eigenvectors = []
    
    C_deflated = [row[:] for row in C] # Deep copy
    
    # Trace for explained variance calculation
    total_variance = sum(C[i][i] for i in range(n_features))
    
    # Extract ALL components
    for _ in range(n_features):
        eig_val, eig_vec = power_iteration(C_deflated)
        eigenvalues.append(eig_val)
        eigenvectors.append(eig_vec)
        
        # Deflate
        term = outer_product(eig_vec, eig_vec)
        term = [[x * eig_val for x in row] for row in term]
        C_deflated = sub_matrix(C_deflated, term)

    # 4. Compute Precision Matrix (Inverse Covariance) via Spectral Inversion
    # Sigma = V * Lambda * V.T
    # Sigma_inv = V * Lambda_inv * V.T
    # Regularize small eigenvalues to avoid explosion
    precision_matrix = zeros(n_features, n_features)
    
    for i in range(n_features):
        lam = eigenvalues[i]
        # Regularization floor (epsilon)
        if lam < 1e-4:
            inv_lam = 0.0 # Ignore noise dimensions
        else:
            inv_lam = 1.0 / lam
            
        v = eigenvectors[i]
        # Add contribution: (1/lam) * v * v.T
        term = outer_product(v, v)
        for r in range(n_features):
            for c in range(n_features):
                precision_matrix[r][c] += inv_lam * term[r][c]
        
    return {
        "components": eigenvectors, 
        "explained_variance": eigenvalues,
        "explained_variance_ratio": [ev / total_variance for ev in eigenvalues] if total_variance > 0 else [0]*n_features,
        "mean": means,
        "std": stds,
        "total_variance": total_variance,
        "precision_matrix": precision_matrix
    }


# =============================================================================
# MAIN SCRIPT
# =============================================================================

def main():
    print("="*60)
    print("  STRUCTURAL PCA (Spectral Diagnostics Enabled)")
    print("="*60)
    
    # 1. Load Data
    data_path = Path("calibration_data_high_dim.json")
    if not data_path.exists():
        print("Data file not found.")
        return
        
    raw = json.loads(data_path.read_text(encoding="utf-8"))
    samples = raw["raw_data"]
    
    # 2. Extract Feature Matrix
    ignore = {"repo", "method", "dominant_file", "context", "total_calls"}
    all_keys = sorted([k for k in samples[0]["metrics"].keys() 
                      if k not in ignore and isinstance(samples[0]["metrics"][k], (int, float))])
    
    # Variance Audit
    active_keys = []
    distributions = raw.get("distributions", {})
    
    print("\nFeature Selection:")
    for k in all_keys:
        var = distributions.get(k, {}).get("variance", 0.0)
        if var > 1e-6:
            active_keys.append(k)
        else:
            # print(f"  [DROP] {k} (var={var})")
            pass
            
    print(f"  Using {len(active_keys)} features.")
    if len(active_keys) < 2:
        return
        
    # Build Matrix X
    X = []
    for s in samples:
        row = [float(s["metrics"].get(k, 0.0)) for k in active_keys]
        X.append(row)
        
    # 3. Running PCA
    print("\nComputing Full Spectrum...")
    result = pca(X)
    
    # 4. Diagnostics Loop (The "Honesty" Check)
    print("\n--- EIGENVALUE SPECTRUM ---")
    cum_var = 0.0
    for i, val in enumerate(result["explained_variance"]):
        ratio = result["explained_variance_ratio"][i]
        cum_var += ratio
        marker = " <--" if i == 2 else "" # Mark cutoff
        print(f"  PC{i+1}: {val:.4f} ({ratio:.1%})  Cum: {cum_var:.1%}{marker}")
        
    # 5. Interpretation of Top 3
    print("\n--- TOP 3 COMPONENTS ---")
    keys = ["Complexity (PC1)", "Resilience (PC2)", "Paradigm (PC3)"]
    for i in range(3):
        pc = result["components"][i]
        print(f"{keys[i]}:")
        # Top loadings
        loadings = [(active_keys[j], pc[j]) for j in range(len(active_keys))]
        loadings.sort(key=lambda x: abs(x[1]), reverse=True)
        print(f"  Top: {', '.join([f'{k}({v:+.2f})' for k,v in loadings[:3]])}")

    # 6. Save Robust Model
    model = {
        "version": "1.1", # Versioning added
        "feature_names": active_keys,
        "mean": result["mean"],
        "std": result["std"],
        "components": result["components"],       # All components
        "explained_variance": result["explained_variance"],
        "precision_matrix": result["precision_matrix"] # For Mahalanobis
    }
    
    Path("structural_pca_model.json").write_text(json.dumps(model, indent=2))
    print("\nModel saved with Precision Matrix for Mahalanobis scoring.")


if __name__ == "__main__":
    main()
