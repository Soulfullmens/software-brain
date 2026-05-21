"""
SmartAgent Demo — "Small Brain + Big Memory" in Action

Run this to see the full architecture working:
    python demo_smart_agent.py

WHAT THIS DEMO SHOWS:
    1. Small model (2-6GB) answering with memory context
    2. One-shot learning (teach once → recognize forever)
    3. Continual learning (gets smarter with every chat)
    4. Memory recall (remembers everything)
    5. Knowledge ingestion (eat text data)
    6. Full agent status report

REQUIREMENTS:
    pip install chromadb sentence-transformers
    
    # Optional (for local inference — recommended):
    # Install Ollama: https://ollama.ai
    # ollama pull phi3:mini
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    print("=" * 60)
    print("  SmartAgent Demo — Small Brain + Big Memory")
    print("  The AI that learns from 1 example and never forgets")
    print("=" * 60)
    print()

    # ── Step 0: Initialize ──
    print("[1/7] Initializing SmartAgent...")
    try:
        from src.agent.smart_agent import SmartAgent
        agent = SmartAgent.from_env(data_dir="./agent_data/smart_demo")
        print("  ✅ SmartAgent initialized")
    except ImportError as e:
        print(f"  ❌ Import error: {e}")
        print("  Run: pip install chromadb sentence-transformers")
        return

    # ── Step 1: Status Check ──
    print()
    print("[2/7] Agent Status:")
    print(agent.status_text())

    # ── Step 2: Teach (Few-Shot Learning) ──
    print()
    print("[3/7] Teaching the agent (one-shot learning)...")

    # Teach it to recognize spam
    result = agent.teach(
        name="spam_email",
        description="Unsolicited bulk commercial email trying to sell something or scam",
        examples=[
            "Buy viagra now! 90% off!",
            "You've won $1,000,000! Click here!",
            "Make money fast working from home",
        ],
        category="email_classification",
    )
    print(f"  ✅ {result}")

    # Teach it to recognize a product
    result = agent.teach(
        name="kitkat",
        description="A chocolate wafer bar made by Nestle, known for its red wrapper and 'Have a Break' slogan",
        examples=[
            "Red wrapper chocolate bar with wafer layers",
            "Break me off a piece of that",
        ],
        category="food",
    )
    print(f"  ✅ {result}")

    # Teach it a coding pattern
    result = agent.teach(
        name="null_pointer_bug",
        description="A bug where code tries to access an attribute or method on a None/null value",
        examples=[
            "AttributeError: 'NoneType' object has no attribute 'split'",
            "TypeError: cannot read property 'length' of null",
        ],
        category="bugs",
    )
    print(f"  ✅ {result}")

    # ── Step 3: Recognize (Zero Retraining) ──
    print()
    print("[4/7] Testing recognition (no retraining!)...")

    tests = [
        ("Congratulations! You've been selected for a $500 gift card!", "email_classification"),
        ("A chocolate bar with crispy layers inside, red packaging", "food"),
        ("crash: NoneType has no attribute 'get'", "bugs"),
    ]

    for text, category in tests:
        result = agent.recognize(text, category=category)
        status = "✅" if result["matched"] else "❌"
        name = result.get("name", "none")
        conf = result.get("confidence", 0)
        print(f"  {status} '{text[:50]}...' → {name} (confidence: {conf:.2f})")

    # ── Step 4: Remember & Recall ──
    print()
    print("[5/7] Testing memory (remember + recall)...")

    agent.remember("Abdul is the owner and creator of Software Brain")
    agent.remember("The project uses FastAPI, Python, and ChromaDB")
    agent.remember("Abdul prefers dark mode and uses VS Code")
    agent.remember("The startup goal is: Small Brain + Big Memory, reduce training costs")
    print("  ✅ Stored 4 facts")

    print()
    print("  Recalling 'Who created this project?':")
    memories = agent.recall("Who created this project?", limit=3)
    for m in memories:
        print(f"    [{m['collection']}|{m['relevance']:.2f}] {m['content'][:80]}")

    print()
    print("  Recalling 'What tech stack is used?':")
    memories = agent.recall("What tech stack is used?", limit=3)
    for m in memories:
        print(f"    [{m['collection']}|{m['relevance']:.2f}] {m['content'][:80]}")

    # ── Step 5: Chat (Memory-Augmented) ──
    print()
    print("[6/7] Testing chat (with memory retrieval)...")
    response = agent.chat("What do you know about me and this project?")
    print(f"  Model: {response.model_used} ({response.provider})")
    print(f"  Memories used: {response.memories_retrieved}")
    print(f"  New facts learned: {response.new_facts_learned}")
    print(f"  Latency: {response.latency_ms:.0f}ms")
    print(f"  Response: {response.content[:200]}...")

    # ── Step 6: Learn a Skill ──
    print()
    print("[7/7] Teaching a skill...")
    result = agent.learn_skill(
        name="deploy_docker",
        description="Deploy the agent using Docker",
        steps=[
            "Build the image: docker build -t software-brain .",
            "Run the container: docker run -p 8000:8000 software-brain",
            "Check health: curl http://localhost:8000/health",
            "View logs: docker logs -f <container_id>",
        ],
    )
    print(f"  ✅ {result}")

    # ── Final Status ──
    print()
    print("=" * 60)
    print("  FINAL STATUS")
    print("=" * 60)
    print(agent.status_text())

    print()
    print("🎯 KEY TAKEAWAY:")
    print("  This agent uses a ~2-6GB model but has UNLIMITED memory.")
    print("  It learned 3 concepts from just 7 examples total.")
    print("  It remembers everything — no retraining needed.")
    print("  It gets smarter with every interaction.")
    print()
    print("  Traditional AI: 175B params = 350GB = massive GPU cluster")
    print("  SmartAgent:     3B params + Vector DB = 2-6GB = your laptop")
    print()
    print("  The memory IS the missing billions of parameters. 🧠")


if __name__ == "__main__":
    main()
