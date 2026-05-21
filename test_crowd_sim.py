"""Test the CrowdSimulator and write output to a file."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.agent.intelligence.crowd_simulator import CrowdSimulator

sim = CrowdSimulator()

# Test: Tesla stock scenario
report = sim.predict(
    scenario="Tesla stock after US goes to war with Iran. Oil prices spiking to $120. EV market uncertainty.",
    population_size=500,
    num_rounds=7,
)
output = sim.format_report(report)

# Write to file (avoid terminal encoding issues)
with open("sim_result.txt", "w", encoding="utf-8") as f:
    f.write(output)

print(f"DONE - {report.population_size} agents, {report.rounds_run} rounds, {report.duration_ms:.0f}ms")
print(f"Consensus: {report.final_consensus} ({report.consensus_confidence:.0f}%)")
print(f"See sim_result.txt for full report")
