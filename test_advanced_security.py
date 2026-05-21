"""
test_advanced_security.py

COMPREHENSIVE VERIFICATION for the 5 Advanced Security & Deployment Upgrades:
1. Network Egress Policy
2. Inference Gateway
3. Operator Approval Flow
4. Filesystem Jail
5. Deployment Blueprint System
"""
import sys
import os
import time
import json
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from agent.security.network_policy import NetworkPolicyEngine, NetworkVerdict, PolicyMode
from agent.security.inference_gateway import InferenceGateway, GatewayVerdict
from agent.security.operator_approval import OperatorApprovalQueue, ApprovalVerdict
from agent.security.filesystem_jail import FilesystemJail, JailViolation
from agent.deployment.blueprint import BlueprintSystem, LifecycleStage

PASSED = 0
FAILED = 0
TOTAL = 0

def test(name, condition, detail=""):
    global PASSED, FAILED, TOTAL
    TOTAL += 1
    if condition:
        PASSED += 1
        print(f"  ✅ {name}")
    else:
        FAILED += 1
        print(f"  ❌ {name} — {detail}")

print("=" * 60)
print("  ADVANCED SECURITY UPGRADES — VERIFICATION")
print("=" * 60)

# ─────────────────────────────────────────
# TEST 1: Network Egress Policy Engine
# ─────────────────────────────────────────
print("\\n── TEST 1: Network Egress Policy Engine ──")

policy = NetworkPolicyEngine()
# Enable permissive mode just for rapid testing to avoid thread blocking
policy.mode = PolicyMode.PERMISSIVE 
policy.allowed_domains = ["*.google.com", "api.anthropic.com"]
policy.blocked_domains = ["*.evil.com", "malware.net"]

# 1. Allowlist testing
result = policy.check_request("https://api.anthropic.com/v1/messages")
test("Allows exact match (api.anthropic.com)", result.verdict == NetworkVerdict.ALLOW)

result = policy.check_request("https://mail.google.com/inbox")
test("Allows glob match (*.google.com)", result.verdict == NetworkVerdict.ALLOW)

# 2. Blocklist testing
result = policy.check_request("http://www.evil.com/steal")
test("Blocks blocklist match (*.evil.com)", result.verdict == NetworkVerdict.BLOCK)

# 3. Port check
result = policy.check_request("http://api.anthropic.com:22/ssh")
test("Blocks invalid ports (22)", result.verdict == NetworkVerdict.BLOCK)

# 4. Strict mode queueing
policy.mode = PolicyMode.STRICT
result = policy.check_request("https://unknown.com/api")
test("Strict Mode: Queues unknown domain", result.verdict == NetworkVerdict.PENDING_APPROVAL)
test("Strict Mode: Logs request ID", result.request_id != "")

pending = policy.get_pending_approvals()
test("Pending queue has 1 item", len(pending) == 1)

# Operator approves
policy.approve_domain("unknown.com")
pending = policy.get_pending_approvals()
test("Approval removes from queue", len(pending) == 0)

result = policy.check_request("https://unknown.com/api")
test("Approved domain is now allowed", result.verdict == NetworkVerdict.ALLOW)

# ─────────────────────────────────────────
# TEST 2: Inference Gateway (PII Masking & Cost)
# ─────────────────────────────────────────
print("\\n── TEST 2: Inference Gateway ──")

gateway = InferenceGateway(daily_budget_usd=1.0)
gateway.set_session("test_session")

# 1. PII Masking
messages = [
    {"role": "user", "content": "My email is john.doe@example.com and my phone is +1-555-123-4567. Here is my key: sk-abc123def456ghi789jkl012mno345pqr"}
]

verdict, _, masked = gateway.intercept_request("anthropic", "claude-3-5", messages)
test("Intercepts and modifies PII", verdict == GatewayVerdict.MODIFY)

content = masked[0]["content"]
test("Masks Email", "[EMAIL_REDACTED]" in content and "john.doe" not in content)
test("Masks Phone", "[PHONE_REDACTED]" in content and "555-123" not in content)
test("Masks API Key", "[API_KEY_REDACTED]" in content and "sk-abc" not in content)

# 2. Local provider bypasses PII
messages_local = [{"role": "user", "content": "Analyze contact: admin@company.com"}]
verdict, _, masked_local = gateway.intercept_request("ollama", "llama3.2", messages_local)
test("Ollama bypasses PII masking", verdict == GatewayVerdict.PASS and "admin@company.com" in masked_local[0]["content"])

# 3. Cost Tracking
gateway.log_response("anthropic", "claude-3-5", 1000, 500, 1200) # $3.00/M in, $15.00/M out -> $0.003 + $0.0075 = $0.0105
stats = gateway.get_stats()
cost = stats["cost"]["daily_cost_usd"]
test("Tracks inference costs correctly", cost > 0.01 and cost < 0.02)

# ─────────────────────────────────────────
# TEST 3: Operator Approval Flow
# ─────────────────────────────────────────
print("\\n── TEST 3: Operator Approval Flow ──")

queue = OperatorApprovalQueue()
# Shorten timeout for tests
req_id = ""

def bg_request():
    global req_id
    verdict = queue.request_approval(
        tool="filesystem", command="delete", 
        params={"path": "critical.db"}, reason="Irreversible", 
        threat="CRITICAL", timeout=2
    )
    # Store result somehow if needed, but we check via stats

t = threading.Thread(target=bg_request)
t.start()
time.sleep(0.1) # Let background thread add to queue

pending = queue.get_pending_requests()
test("Request added to approval queue", len(pending) == 1)
req_id = pending[0]["request_id"]

# Operator approves
queue.resolve_request(req_id, ApprovalVerdict.APPROVED, create_rule=True)
t.join()

test("Operator resolution works", queue.stats["approved"] == 1)
test("Persistent rule created", len(queue._rules) == 1)

# Persistent rule auto-handles next identical request
verdict = queue.request_approval(
    tool="filesystem", command="delete", 
    params={"path": "critical.db"}, reason="Irreversible", threat="CRITICAL"
)
test("Persistent rule auto-approves", verdict == ApprovalVerdict.APPROVED)
test("Auto-handled logged", queue.stats["auto_handled"] == 1)

queue.shutdown()

# ─────────────────────────────────────────
# TEST 4: Filesystem Jail (Confinement & Snapshots)
# ─────────────────────────────────────────
print("\\n── TEST 4: Filesystem Jail ──")

# Temp workspace for tests
with tempfile.TemporaryDirectory() as temp_dir:
    jail = FilesystemJail(workspace_root=temp_dir, max_session_writes_mb=1.0)
    
    # 1. Path resolution (safe)
    safe_target = os.path.join(temp_dir, "test.txt")
    resolved = jail.resolve_path(safe_target)
    test("Safe path resolves correctly", resolved == safe_target)
    
    # 2. Path Traversal Prevention
    try:
        jail.resolve_path(os.path.join(temp_dir, "../../etc/passwd"))
        test("Blocks path traversal", False, "Failed to raise JailViolation")
    except JailViolation:
        test("Blocks path traversal", True)
        
    try:
        if os.name == 'nt':
            jail.resolve_path("C:\\Windows\\System32")
        else:
            jail.resolve_path("/etc/shadow")
        test("Blocks absolute external paths", False, "Failed to raise JailViolation")
    except JailViolation:
        test("Blocks absolute external paths", True)
        
    # 3. Pre-execution Snapshots
    with open(safe_target, "w") as f:
        f.write("Original Content")
        
    snap_id = jail.snapshot_file(safe_target)
    test("Creates pre-execution snapshot", snap_id is not None)
    
    with open(safe_target, "w") as f:
        f.write("Malicious modification!")
        
    restored = jail.restore_snapshot(snap_id)
    test("Successfully restores snapshot", restored)
    
    with open(safe_target, "r") as f:
        content = f.read()
    test("Content verified rolled back", content == "Original Content")
    
    # 4. Write Budgets
    try:
        jail.check_write_budget(2 * 1024 * 1024) # 2MB (limit is 1MB)
        test("Enforces write budgets", False, "Allowed write over budget")
    except JailViolation:
        test("Enforces write budgets", True)

# ─────────────────────────────────────────
# TEST 5: Deployment Blueprint System
# ─────────────────────────────────────────
print("\\n── TEST 5: Deployment Blueprint System ──")

# Assuming config/blueprint.yaml exists from our generation
bp = BlueprintSystem()
try:
    bp._resolve()
    test("Blueprint Resolve Phase (Parses Manifest)", bp.config.get("name") == "agentic-engine-pro-secure")
    test("Blueprint parses components", len(bp.components) >= 3)
    
    # Avoid actually running full deployments in tests, but verify logic works
    stage = bp.stage
    test("Blueprint defaults to INIT stage", stage == LifecycleStage.INIT)
except Exception as e:
    test(f"Blueprint system checks", False, f"Failed: {e}")

# ─────────────────────────────────────────
# RESULTS
# ─────────────────────────────────────────

print("\\n" + "=" * 60)
print(f"  RESULTS: {PASSED}/{TOTAL} passed")
if FAILED > 0:
    print(f"  ❌ {FAILED} FAILED")
else:
    print(f"  ✅ ALL {TOTAL} TESTS PASSED")
print("=" * 60)

sys.exit(0 if FAILED == 0 else 1)
