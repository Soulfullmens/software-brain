"""
cli.py — Jarvis V2 Developer Co-Pilot CLI.

Commands:
  jarvis watch           — Watch current directory, warn before runs
  jarvis check FILE      — Pre-run check on a specific file
  jarvis history         — Show error history + stats
  jarvis status          — Session status
  jarvis explain         — LLM explain last error
  jarvis experiment      — Log experiment event / show summary
  jarvis help            — Show commands

Usage:
  python -m jarvis_v2.cli watch
  python -m jarvis_v2.cli check main.py
"""
import sys, os, argparse, json, time

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis_v2.jarvis_dev import JarvisDev


def main():
    parser = argparse.ArgumentParser(
        description="Jarvis V2 — Developer Workflow Co-Pilot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  check FILE     Pre-run check on a file (the core feature)
  history        Show error history and stats
  status         Session and interrupt stats
  explain TEXT   LLM explain an error
  log TYPE       Log experiment event (saved/annoyed/missed/wrong/silent)
  experiment     Show 14-day experiment summary
  repl           Interactive mode
        """
    )
    parser.add_argument("command", nargs="?", default="repl",
                       help="Command to run")
    parser.add_argument("args", nargs="*", help="Command arguments")
    parser.add_argument("--memory", help="Custom memory file path")
    
    args = parser.parse_args()
    pilot = JarvisDev(memory_file=args.memory)
    
    if args.command == "check":
        _cmd_check(pilot, args.args)
    elif args.command == "history":
        _cmd_history(pilot)
    elif args.command == "status":
        print(pilot.display_status())
    elif args.command == "explain":
        _cmd_explain(pilot, args.args)
    elif args.command == "log":
        _cmd_log(pilot, args.args)
    elif args.command == "experiment":
        _cmd_experiment(pilot)
    elif args.command == "repl":
        _cmd_repl(pilot)
    elif args.command == "help":
        parser.print_help()
    else:
        print(f"Unknown command: {args.command}")
        parser.print_help()


def _cmd_check(pilot: JarvisDev, args):
    """Pre-run check on a file."""
    if not args:
        print("Usage: jarvis check <file>")
        return
    
    file_path = args[0]
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return
    
    command = f"python {file_path}"
    warnings = pilot.check_before_run(command, file_path)
    
    if not warnings:
        print(f"  ✅ No risks detected in {os.path.basename(file_path)}")
        return
    
    print(f"\n  ⚠️  Pre-run warnings for {os.path.basename(file_path)}:")
    print("  " + "─" * 40)
    
    for i, w in enumerate(warnings, 1):
        icon = "⚠️" if w["type"] == "warning" else "🤔"
        print(f"  {i}. {icon} {w['message']}")
        if w.get("line_hint"):
            print(f"     Line ~{w['line_hint']}")
        print(f"     Confidence: {w['confidence']:.0%} | Severity: {w['severity']}s")
        print()


def _cmd_history(pilot: JarvisDev):
    """Show error history."""
    stats = pilot.memory.stats()
    
    if stats["total"] == 0:
        print("  No errors recorded yet. Start coding!")
        return
    
    print("\n  📊 Error History")
    print("  " + "─" * 40)
    print(f"  Total errors: {stats['total']}")
    
    if stats['classes']:
        print("\n  Top error classes:")
        for cls, count in stats['classes'].items():
            print(f"    {cls}: {count}")
    
    if stats['worst_files']:
        print("\n  Most error-prone files:")
        for f in stats['worst_files']:
            print(f"    {f['file']}: {f['errors']} errors")
    
    if stats.get('estimated_time_wasted_minutes'):
        print(f"\n  ⏱ Estimated time wasted: {stats['estimated_time_wasted_minutes']} minutes")
    print()


def _cmd_explain(pilot: JarvisDev, args):
    """LLM explain an error."""
    text = " ".join(args) if args else ""
    if not text:
        print("Usage: jarvis explain <paste traceback>")
        return
    
    print("  🧠 Asking LLM...")
    result = pilot.explain_error(text)
    
    if result["success"]:
        print(f"\n  {result['explanation']}")
        print(f"\n  (via {result['model']})")
    else:
        print(f"  ❌ LLM not available: {result.get('fallback_reason', 'unknown')}")
        print("  Install Ollama: https://ollama.ai")


def _cmd_log(pilot: JarvisDev, args):
    """Log an experiment event."""
    valid_types = ["saved", "annoyed", "missed", "wrong", "silent"]
    
    if not args or args[0] not in valid_types:
        print(f"  Usage: jarvis log <{'|'.join(valid_types)}> [detail] [time_saved_seconds]")
        return
    
    event_type = args[0]
    detail = args[1] if len(args) > 1 else ""
    time_saved = int(args[2]) if len(args) > 2 else 0
    
    result = pilot.log_experiment(event_type, detail, time_saved)
    print(f"  📝 Logged: {event_type}" + (f" ({detail})" if detail else ""))


def _cmd_experiment(pilot: JarvisDev):
    """Show experiment summary."""
    summary = pilot.experiment_summary()
    
    if summary.get("total_events", 0) == 0:
        print("  No experiment data yet.")
        print("  Log events with: jarvis log saved|annoyed|missed|wrong|silent")
        return
    
    print("\n  📊 14-Day Experiment Summary")
    print("  " + "─" * 40)
    print(f"  Days tracked: {summary['days_tracked']}")
    print(f"  Total events: {summary['total_events']}")
    print(f"  ✅ Saved me:  {summary['saved']}")
    print(f"  😤 Annoyed me: {summary['annoyed']}")
    print(f"  😢 Missed:     {summary['missed']}")
    print(f"  ❌ Wrong:      {summary['wrong']}")
    print(f"  🤫 Should silence: {summary['silent_should_be']}")
    print(f"  ⏱ Time saved: {summary['total_time_saved_minutes']} min")
    print(f"\n  Verdict: {summary['verdict']}")
    print()


def _cmd_repl(pilot: JarvisDev):
    """Interactive REPL."""
    print("\n" + "═" * 45)
    print("  🧠 JARVIS V2 — Developer Co-Pilot")
    print("  Python. VS Code. Nothing else.")
    print("═" * 45)
    print("  Commands: check <file> | history | status | explain | help | quit")
    print()
    
    while True:
        try:
            cmd = input("jarvis> ").strip()
            
            if cmd in ("quit", "exit", "q"):
                summary = pilot.experiment_summary()
                if summary.get("total_events", 0) > 0:
                    print(f"\n  Session saved. Verdict: {summary['verdict']}")
                print("  👋 See you next session.\n")
                break
            
            elif cmd.startswith("check "):
                file_path = cmd.split(None, 1)[1]
                _cmd_check(pilot, [file_path])
            
            elif cmd.startswith("error "):
                # Record error: error <paste traceback>
                tb = cmd.split(None, 1)[1]
                result = pilot.record_error(tb)
                print(f"  📝 {result['error_class']} (seen {result['times_seen']}x)")
                if result.get("stuck"):
                    print(f"  {result['stuck_message']}")
                elif result.get("is_repeat"):
                    print(f"  {result['repeat_message']}")
            
            elif cmd == "history":
                _cmd_history(pilot)
            
            elif cmd == "status":
                print(pilot.display_status())
            
            elif cmd.startswith("explain "):
                _cmd_explain(pilot, cmd.split(None, 1)[1:])
            
            elif cmd.startswith("log "):
                _cmd_log(pilot, cmd.split()[1:])
            
            elif cmd == "experiment":
                _cmd_experiment(pilot)
            
            elif cmd == "flow":
                print(f"  {pilot.session.get_flow_summary()}")
            
            elif cmd == "dismiss":
                pilot.dismiss_warning()
                print("  Noted — threshold raised.")
            
            elif cmd == "useful":
                pilot.accept_warning()
                print("  Thanks — noted as useful.")
            
            elif cmd == "help":
                print("  check <file>   — Pre-run risk check (THE feature)")
                print("  error <text>   — Record an error traceback")
                print("  history        — Error stats & patterns")
                print("  status         — Session & interrupt stats")
                print("  explain <text> — LLM explain error")
                print("  flow           — Session flow summary")
                print("  log <type>     — Experiment event (saved/annoyed/missed/wrong/silent)")
                print("  experiment     — 14-day experiment summary")
                print("  dismiss        — Dismiss last warning (raises threshold)")
                print("  useful         — Mark last warning as useful")
                print("  quit           — Exit")
            
            elif cmd == "":
                continue
            
            else:
                print(f"  Unknown: '{cmd}'. Type 'help'.")
        
        except KeyboardInterrupt:
            print("\n  👋 Bye.\n")
            break
        except Exception as e:
            print(f"  Error: {e}")


if __name__ == "__main__":
    main()
