"""Quick test for the Knowledge Harvester."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from src.agent.intelligence.knowledge_harvester import KnowledgeHarvester

print("=== Testing Knowledge Harvester ===")
h = KnowledgeHarvester()

# Test 1: Harvest from Wikipedia
print("\n--- Harvest: python programming ---")
r = h.harvest(['python programming'], max_pages_per_topic=3, max_workers=1)
print(f"Result: {r['total_pages_accepted']} accepted out of {r['total_pages_crawled']}")
print(f"KB items: {r['knowledge_base_stats']['total_knowledge_items']}")
print(f"Acceptance rate: {r['acceptance_rate']}%")

# Test 2: Search
print("\n--- Search: python ---")
results = h.search_knowledge("python")
print(results[:500] if results else "No results")

# Test 3: Stats
print("\n--- Stats ---")
import json
stats = h.store.get_stats()
print(json.dumps(stats, indent=2))

print("\n=== DONE ===")
