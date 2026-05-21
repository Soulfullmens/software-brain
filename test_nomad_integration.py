"""
test_nomad_integration.py — Test suite for Phase 5 Project Nomad upgrades
"""
import sys
import os
import time
import tempfile
import shutil
import unittest.mock as mock

# Add project to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

RESULTS = {"passed": 0, "failed": 0, "tests": []}

def test(name, condition, details=""):
    """Test helper."""
    status = "PASS" if condition else "FAIL"
    RESULTS["passed" if condition else "failed"] += 1
    RESULTS["tests"].append({"name": name, "status": status})
    icon = "✅" if condition else "❌"
    print(f"  {icon} {name}" + (f" — {details}" if details else ""))

def run_all_tests():
    print("=" * 60)
    print("  PHASE 5: PROJECT NOMAD INTEGRATION")
    print("  Airgap Enforcer, Offline Tools, Nomad Orchestrator, Web Archiver")
    print("=" * 60)

    test_container_orchestrator()
    test_airgap_mode()
    test_offline_tools()
    test_web_archiver()

    print("\n" + "=" * 60)
    total = RESULTS["passed"] + RESULTS["failed"]
    print(f"  RESULTS: {RESULTS['passed']}/{total} passed")
    if RESULTS["failed"] == 0:
        print("  🎉 ALL TESTS PASSED")
    else:
        print(f"  ⚠️  {RESULTS['failed']} FAILED")
    print("=" * 60)

# ═══════════════════════════════════════════════════════
# 1. ORCHESTRATOR TESTS
# ═══════════════════════════════════════════════════════
def test_container_orchestrator():
    print("\n🐳 [1/4] Nomad Container Orchestrator")
    from agent.nomad.container_orchestrator import NomadOrchestrator
    import subprocess

    with mock.patch("subprocess.run") as mock_run:
        # Mock checking docker installed
        mock_result = mock.Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Docker version 24.0.0"
        mock_run.return_value = mock_result

        orchestrator = NomadOrchestrator()
        test("Orchestrator loaded", orchestrator is not None)

        # Mock deploy
        orchestrator.deploy_kiwix("/tmp/library")
        mock_run.assert_called()
        cmd = mock_run.call_args[0][0]
        test("Deploy command formats properly", "docker" in cmd and "run" in cmd and "kiwix" in cmd[-1])

# ═══════════════════════════════════════════════════════
# 2. AIRGAP MODE TESTS
# ═══════════════════════════════════════════════════════
def test_airgap_mode():
    print("\n🔌 [2/4] Airgap Execution Enforcer")
    from agent.nomad.airgap_mode import AirgapEnforcer
    import socket

    enforcer = AirgapEnforcer()
    
    # Test tool filtering
    class MockTool:
        def __init__(self, name):
            self.name = name
    
    tools = [MockTool("search_google"), MockTool("local_calc")]
    filtered = enforcer.filter_tools(tools, ["search_google"])
    test("Filter tools leaves alone when off", len(filtered) == 2)
    
    # Enable Airgap
    enforcer.enable()
    filtered = enforcer.filter_tools(tools, ["search_google"])
    test("Filter tools strips internet tools when on", len(filtered) == 1 and filtered[0].name == "local_calc")

    import urllib.request
    try:
        urllib.request.urlopen("http://google.com", timeout=2) # Try to connect via hostname
        blocked = False
    except ConnectionError:
        blocked = True
    except Exception as e:
        if "[AIRGAP ENFORCER]" in str(e):
            blocked = True
        else:
            blocked = False
        
    test("External socket connection blocked", blocked)
    
    # Allowed local connection
    local_passed = False
    try:
        urllib.request.urlopen("http://127.0.0.1:9999", timeout=1)
    except ConnectionError as e:
        if "[AIRGAP ENFORCER]" in str(e):
            local_passed = False
        else:
            local_passed = True # Connection refused is normal
    except Exception:
        local_passed = True
        
    test("Localhost connection allowed", local_passed)

    enforcer.disable()

# ═══════════════════════════════════════════════════════
# 3. OFFLINE TOOLS TESTS
# ═══════════════════════════════════════════════════════
def test_offline_tools():
    print("\n⚙️  [3/4] Offline Cyberchef Tools")
    from agent.nomad.offline_tools import CyberChefLocal

    test("Base64 Encode", CyberChefLocal.to_base64("hello world") == "aGVsbG8gd29ybGQ=")
    test("Base64 Decode", CyberChefLocal.from_base64("aGVsbG8gd29ybGQ=") == "hello world")
    
    test("Hex Encode", CyberChefLocal.to_hex("hello") == "68656c6c6f")
    test("Hex Decode", CyberChefLocal.from_hex("68656c6c6f") == "hello")
    
    hash_val = CyberChefLocal.sha256_hash("test")
    test("SHA-256 Hash", len(hash_val) == 64)
    
    magic = CyberChefLocal.magic_decode("616c696365") # "alice" in hex
    test("Magic Decode", magic == "alice", f"Output was: {magic}")


# ═══════════════════════════════════════════════════════
# 4. WEB ARCHIVER TESTS
# ═══════════════════════════════════════════════════════
def test_web_archiver():
    print("\n🕸️  [4/4] Web Archiver (Pre-Offline Caching)")
    import urllib.request
    from agent.nomad.web_archiver import WebArchiver, SimpleHTMLTextExtractor
    from agent.intelligence.knowledge_graph import KnowledgeGraph

    # Mock response
    mock_response = mock.Mock()
    mock_response.read.return_value = b"<html><head><title>Test</title></head><body><h1>Hello World</h1><script>ignore this</script></body></html>"
    mock_response.__enter__ = mock.Mock(return_value=mock_response)
    mock_response.__exit__ = mock.Mock(return_value=None)
    
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
        
    try:
        kg = KnowledgeGraph(storage_path=path)
        archiver = WebArchiver(kg)
        
        with mock.patch.object(urllib.request, "urlopen", return_value=mock_response):
            archiver.archive_url("https://projectnomad.us", "Nomad Project")
            
        # Check graph
        results = kg.search("World")
        test("Scraped text appended to graph", len(results.facts) > 0, f"Facts: {results.facts}")
        
    finally:
        os.unlink(path)

if __name__ == "__main__":
    run_all_tests()
