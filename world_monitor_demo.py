"""
world_monitor_demo.py
Demonstrates the World Monitor tool integrated into our Agent.
"""
import sys
import os

# Ensure src is in the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.agent.tools.world_monitor import WorldMonitorTool

def run_demo():
    print("\n" + "="*50)
    print("WORLD MONITOR AGENT INTEGRATION DEMO")
    print("="*50 + "\n")
    
    tool = WorldMonitorTool()
    
    print("1. Fetching Latest Global Incidents...")
    incidents = tool.run("get_latest_incidents", region="Global", limit=2)
    for inc in incidents:
        print(f"  [{inc['severity']}] {inc['type']} in {inc['region']}: {inc['headline']}")
        
    print("\n2. Checking Critical Infrastructure Health...")
    infra = tool.run("check_infrastructure", target_type="Undersea Cables")
    print(f"  Target: {infra['infrastructure_type']}")
    print(f"  Status: {infra['overall_health']}")
    print(f"  Details: {infra['details']}")
    
    print("\n3. Querying Country Instability Index (CII)...")
    status = tool.run("query_country_status", country_code="US")
    print(f"  Country: {status['country_code']}")
    print(f"  Instability Score: {status['instability_index']} / 10")
    print(f"  Active Threats: {', '.join(status['active_threats'])}")
    
    print("\n" + "="*50)
    print("This tool allows your Autonomous Agent to check geopolitical")
    print("and infrastructural safety before taking actions.")
    print("="*50 + "\n")

if __name__ == "__main__":
    run_demo()
