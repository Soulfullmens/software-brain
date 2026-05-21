"""
main.py — The Autonomous NOMAD Swarm Command Line Interface

Entrypoint for interacting with the fully upgraded Agentic Engine Pro.
Integrates the Swarm Orchestrator (MiroFish) and Airgap Enforcer (Nomad) into a single console dashboard.
"""
import sys
import os
import time

# Ensure src is in python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

try:
    from agent.intelligence.swarm_orchestrator import SwarmOrchestrator
    from agent.intelligence.persona_engine import PersonaEngine
    from agent.intelligence.knowledge_graph import KnowledgeGraph
    from agent.nomad.airgap_mode import AirgapEnforcer
    from agent.nomad.web_archiver import WebArchiver
except ImportError as e:
    print(f"Failed to load core agent modules: {e}")
    print("Ensure all dependencies (Phase 2-5) are built correctly.")
    sys.exit(1)

# Soft load Router
try:
    from agent.llm_router import LLMRouter, LLMRequest, Message, Role
    HAS_LLM = True
except ImportError:
    HAS_LLM = False


class SwarmCLI:
    def __init__(self):
        self.kg = KnowledgeGraph(storage_path=os.path.join(os.path.dirname(__file__), "agent_data", "knowledge_graph.json"))
        
        # LLM wrapper for the Swarm
        def llm_generate(prompt: str) -> str:
            if HAS_LLM:
                try:
                    if not hasattr(self, 'router'):
                        self.router = LLMRouter.from_env() # load from env natively!
                    
                    request = LLMRequest(messages=[Message(role=Role.USER, content=prompt)], max_tokens=2000)
                    response = self.router.generate(request=request)
                    return response.content
                except Exception as e:
                    return f'Thought: LLM Setup Error: {e}. Please add your API key to `.env` or run Ollama!\nAction: finish\nObservation: {{"status":"error", "details":"Missing keys"}}'
            
            # Fallback mock for testing without API keys offline
            mock_explanation = (
                "To make me really think, you need a 'Brain'!\n"
                "1. If you are online: Add your OpenRouter API key to the `.env` file.\n"
                "2. IF THE INTERNET IS DEAD: Download `Ollama` and run a local model like `llama3`. No API keys required ever."
            )
            return f'Thought: {mock_explanation}\nAction: finish\nObservation: {{"status":"success", "details":"Waiting for LLM Setup."}}'
            
        self.persona_engine = PersonaEngine()
        self.orchestrator = SwarmOrchestrator(
            llm_fn=llm_generate,
            persona_engine=self.persona_engine,
            base_tools=[] # We can inject tools here if needed
        )
        
        self.airgap = AirgapEnforcer()
        self.archiver = WebArchiver(self.kg)
        
    def clear_screen(self):
        os.system('cls' if os.name == 'nt' else 'clear')

    def print_header(self):
        self.clear_screen()
        print("=" * 60)
        print(" 🧠 NOMAD SWARM TERMINAL v1.0 🧠 ".center(60))
        print("=" * 60)
        
        airgap_stat = "🟢 ACTIVE (Bunker Mode)" if self.airgap.is_active else "🔴 INACTIVE (Online)"
        
        entities = len(self.kg.nodes) if hasattr(self.kg, 'nodes') else 0
        edges = sum(len(e) for e in getattr(self.kg, 'edges', {}).values()) if hasattr(self.kg, 'edges') else 0
        
        print(f" Airgap Survival Mode : {airgap_stat}")
        print(f" Knowledge Graph      : {entities} Entities, {edges} Relationships")
        print("-" * 60)

    def run(self):
        while True:
            self.print_header()
            print("1. 🗣️  Chat / Execute Task (Swarm Mode)")
            print("2. 🔌 Toggle Airgap Survival Mode")
            print("3. 🕸️  Web Archiver (Cache URL for Offline)")
            print("4. 🧠 View Knowledge Graph Memory")
            print("5. 🚪 Exit")
            print()
            try:
                choice = input("Select an option > ").strip()
            except KeyboardInterrupt:
                break
                
            if choice == '1':
                self.chat_loop()
            elif choice == '2':
                self.toggle_airgap()
            elif choice == '3':
                self.run_archiver()
            elif choice == '4':
                self.view_graph()
            elif choice == '5':
                print("Shutting down Swarm Terminal...")
                break
            else:
                print("Invalid choice.")
                time.sleep(1)

    def chat_loop(self):
        self.print_header()
        print("Enter 'back' to return to menu.\n")
        while True:
            print("="*60)
            prompt = input("👤 You > ").strip()
            if prompt.lower() in ('back', 'exit', 'quit'):
                break
            if not prompt: continue
            
            print("\n🤖 Swarm Orchestrator initializing parallel agents...")
            try:
                result = self.orchestrator.orchestrate(prompt)
                print("\n" + "="*60)
                print("🏆 FINAL SWARM SYNTHESIS:")
                print(result.final_synthesis)
                print("="*60)
                
                print(f"\n[Worker Threads Executed: {len(result.worker_results)}]")
                
            except Exception as e:
                print(f"\n❌ Swarm Execution Failed: {e}")
                
            input("\nPress Enter to continue...")
            self.print_header()

    def toggle_airgap(self):
        if self.airgap.is_active:
            self.airgap.disable()
            print("\n🌐 Internet Connectivity Restored.")
        else:
            self.airgap.enable()
            print("\n🔌 AIRGAP ENABLED. Welcome to the bunker.")
        time.sleep(1.5)

    def run_archiver(self):
        if self.airgap.is_active:
            print("\n❌ Cannot use Web Archiver while Airgap Mode is active. Turn on internet first.")
            time.sleep(2)
            return
            
        print("\n🕸️  NOMAD Web Archiver")
        url = input("Enter URL to archive offline > ").strip()
        if not url: return
        topic = input("Enter a Topic Category for this URL > ").strip()
        
        print(f"\nArchiving {url}...")
        success = self.archiver.archive_url(url, topic)
        if success:
            print("✅ Successfully cached into local Knowledge Graph.")
        else:
            print("❌ Archiving failed.")
        time.sleep(2)
        
    def view_graph(self):
        self.print_header()
        query = input("Enter search term (or press enter for overview) > ").strip()
        
        if not query:
            print("\nGraph Overview:")
            entities = list(getattr(self.kg, 'nodes', {}).keys())[:10]
            print(f"Top entities: {', '.join(entities)}")
        else:
            print("\nSearching...")
            results = self.kg.search(query)
            if results and results.facts:
                for idx, fact in enumerate(results.facts):
                    print(f"- {fact}")
            else:
                print("No relevant facts found offline.")
                
        input("\nPress Enter to return...")

if __name__ == "__main__":
    try:
        cli = SwarmCLI()
        cli.run()
    except Exception as e:
        print(f"Fatal Error starting CLI: {e}")
