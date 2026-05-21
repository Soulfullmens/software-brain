"""
logger.py

Structured JSON Logger for Workflow Observability.
"""
import os
import json
import uuid
import time
from typing import Dict, Any, List
from ...config import config

class WorkflowLogger:
    def __init__(self):
        self.log_dir = config.paths.get("logs", "./logs")
        self.current_run_id = None
        self.run_data = {}

    def start_run(self, goal: str) -> str:
        self.current_run_id = str(uuid.uuid4())
        self.run_data = {
            "run_id": self.current_run_id,
            "timestamp": _get_timestamp(),
            "goal": goal,
            "status": "RUNNING",
            "steps": [],
            "artifacts": [],
            "errors": []
        }
        self._save_run()
        return self.current_run_id

    def log_step(self, step_name: str, tool: str, status: str, result: Any):
        step_record = {
            "timestamp": _get_timestamp(),
            "step": step_name,
            "tool": tool,
            "status": status,
            "result": str(result)[:500] # Truncate large outputs
        }
        self.run_data["steps"].append(step_record)
        self._save_run()

    def log_error(self, step_name: str, error: str):
        error_record = {
            "timestamp": _get_timestamp(),
            "step": step_name,
            "error": str(error)
        }
        self.run_data["errors"].append(error_record)
        self._save_run()

    def end_run(self, status: str, artifacts: List[str] = []):
        self.run_data["status"] = status
        self.run_data["end_time"] = _get_timestamp()
        self.run_data["artifacts"] = artifacts
        self.run_data["duration_seconds"] = _compute_duration(self.run_data["timestamp"], self.run_data["end_time"])
        self._save_run()
        print(f"[Logger] Run {self.current_run_id} finished: {status}")

    def _save_run(self):
        if not self.current_run_id:
            return
        
        # Organize by date
        date_str = time.strftime("%Y-%m-%d")
        daily_pid_dir = os.path.join(self.log_dir, date_str)
        os.makedirs(daily_pid_dir, exist_ok=True)
        
        filepath = os.path.join(daily_pid_dir, f"{self.current_run_id}.json")
        try:
            with open(filepath, "w") as f:
                json.dump(self.run_data, f, indent=2)
        except Exception as e:
            print(f"[Logger] Failed to save log: {e}")

def _get_timestamp():
    return time.strftime("%Y-%m-%d %H:%M:%S")

def _compute_duration(start_str, end_str):
    # Simplistic duration
    import datetime
    fmt =("%Y-%m-%d %H:%M:%S")
    t1 = datetime.datetime.strptime(start_str, fmt)
    t2 = datetime.datetime.strptime(end_str, fmt)
    return (t2 - t1).total_seconds()
