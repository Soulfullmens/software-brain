import json

lines = open(r"c:\Users\abdul rahaman\OneDrive\Ai software\software-brain\phase_p_mvp\data\traces\trace.log").readlines()
for line in lines:
    if not line.strip():
        continue
    data = json.loads(line.strip())
    t = data["type"]
    
    if t == "FINAL_RESPONSE":
        print("Recursion depth:", data["recursion_depth"])
        print("Chunks explored:", data["chunks_explored"], "/", data["total_chunks"])
        print("Discriminating probes:", data["discriminating_probes"], "(", data["probes_resolved"], "resolved)")
        print()
        for h in data["hypotheses"]:
            status = h["status"]
            conf = h["confidence"]
            stmt = h["statement"]
            sup = h["supporting_count"]
            con = h["contradicting_count"]
            gaps = len(h["unresolved_gaps"])
            absence = h["absence_penalties"]
            print("  [{}] (conf={:.2f}) {}".format(status, conf, stmt))
            print("    supporting={}, contradicting={}, gaps={}, absence={}".format(sup, con, gaps, absence))
            for g in h["unresolved_gaps"]:
                print("    MISSING:", g)
    elif t == "CONTINUED_EXPLORATION":
        cs = data.get("from_callsites", [])
        gs = data.get("from_gaps", [])
        reason = data.get("reason", "")
        print("CONTINUED: callsites={}, gaps={}, reason={}".format(cs, gs, reason))
    elif t == "DISCRIMINATION_PROBES":
        print("PROBES: total={}, resolved={}".format(data["total_probes"], data["resolved"]))
        for p in data.get("probes", []):
            icon = "Y" if p["found"] else "N"
            print("  [{}] {} -> supports: {}".format(icon, p["desc"], p["supports"]))
