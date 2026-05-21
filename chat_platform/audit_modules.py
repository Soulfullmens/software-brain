"""Quick audit script — verifies all modules import cleanly."""
import sys, importlib, os, traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

modules = [
    'src.agent.security.network_policy',
    'src.agent.security.inference_gateway',
    'src.agent.security.operator_approval',
    'src.agent.security.filesystem_jail',
    'src.agent.security.security_kernel',
    'src.agent.intelligence.react_loop',
    'src.agent.intelligence.swarm_orchestrator',
    'src.agent.intelligence.insight_daemon',
    'src.agent.intelligence.dynamic_tool_creator',
    'src.agent.deployment.blueprint',
    'src.agent.nomad.airgap_mode',
    'src.agent.nomad.container_orchestrator',
    'src.agent.nomad.offline_tools',
    'src.agent.nomad.web_archiver',
]

print("=" * 60)
print(" NOMAD AGENT MODULE IMPORT AUDIT")
print("=" * 60)

ok = 0
fail = 0
for m in modules:
    try:
        mod = importlib.import_module(m)
        size = os.path.getsize(mod.__file__) if hasattr(mod, '__file__') and mod.__file__ else 0
        print(f"  OK   {m} ({size} bytes)")
        ok += 1
    except Exception as e:
        print(f"  FAIL {m}: {e}")
        fail += 1

# Also check chat platform files exist
chat_files = [
    'chat_platform/server.py',
    'chat_platform/db.py',
    'chat_platform/crypto.py',
    'chat_platform/translator.py',
    'chat_platform/agent_bridge.py',
    'chat_platform/static/index.html',
    'chat_platform/static/style.css',
    'chat_platform/static/app.js',
    'chat_platform/static/sw.js',
    'chat_platform/static/manifest.json',
    'config/network_policy.yaml',
    'config/blueprint.yaml',
    'Dockerfile',
    'main.py',
]

print("\n" + "=" * 60)
print(" CHAT PLATFORM FILE CHECK")
print("=" * 60)
for f in chat_files:
    full = os.path.join(os.path.dirname(os.path.dirname(__file__)), f)
    if os.path.exists(full):
        sz = os.path.getsize(full)
        print(f"  OK   {f} ({sz} bytes)")
        ok += 1
    else:
        print(f"  MISS {f}")
        fail += 1

print(f"\n  TOTAL: {ok} OK, {fail} FAILED")
print("=" * 60)
