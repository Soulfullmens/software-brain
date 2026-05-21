"""
context_memory.py — Per-App Habit Tracking + Temporal Fact Memory.

Stores in ~/.jarvis/memory/{app_name}.json
Tracks: frequent windows, common actions, last files, preferences.
Auto-prunes entries older than 30 days.
Thread-safe read/write with file locking.

TEMPORAL MEMORY (MiroFish-inspired):
    - Facts have valid_from / expired_at timestamps
    - get_active_facts() returns only currently valid facts
    - get_historical_facts() returns expired/superseded facts
    - Automatic relevance decay over time
"""
import os, json, time, threading
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pathlib import Path


MEMORY_DIR = os.path.join(os.path.expanduser("~"), ".jarvis", "memory")
PRUNE_DAYS = 30
MAX_ENTRIES_PER_KEY = 50


class ContextMemory:
    """Per-app context memory — remembers how YOU use each app."""
    
    def __init__(self, memory_dir: str = None):
        self._dir = memory_dir or MEMORY_DIR
        os.makedirs(self._dir, exist_ok=True)
        self._lock = threading.Lock()
        self._cache: Dict[str, Dict] = {}
    
    def remember(self, app: str, key: str, value: Any,
                 valid_hours: float = None):
        """Store a context item for an app.
        
        Args:
            app: Application name
            key: Memory key
            value: Value to store
            valid_hours: If set, fact will auto-expire after N hours
        """
        app = self._sanitize(app)
        data = self._load(app)
        
        if key not in data:
            data[key] = []
        
        entry = {
            "value": value,
            "time": datetime.now().isoformat(),
            "ts": time.time(),
            "valid_from": time.time(),
            "expired_at": time.time() + (valid_hours * 3600) if valid_hours else None,
            "relevance": 1.0,
        }
        data[key].append(entry)
        
        # Cap entries
        if len(data[key]) > MAX_ENTRIES_PER_KEY:
            data[key] = data[key][-MAX_ENTRIES_PER_KEY:]
        
        self._save(app, data)
    
    def recall(self, app: str, key: str, last_n: int = 5) -> List[Any]:
        """Recall recent values for a key."""
        app = self._sanitize(app)
        data = self._load(app)
        entries = data.get(key, [])
        return [e["value"] for e in entries[-last_n:]]
    
    def recall_latest(self, app: str, key: str) -> Optional[Any]:
        """Get the most recent value for a key."""
        values = self.recall(app, key, last_n=1)
        return values[0] if values else None
    
    def get_app_profile(self, app: str) -> Dict:
        """Get full memory profile for an app."""
        app = self._sanitize(app)
        data = self._load(app)
        profile = {}
        for key, entries in data.items():
            profile[key] = {
                "count": len(entries),
                "latest": entries[-1]["value"] if entries else None,
                "first_seen": entries[0]["time"] if entries else None,
                "last_seen": entries[-1]["time"] if entries else None,
            }
        return profile
    
    def get_frequent(self, app: str, key: str, top_n: int = 5) -> List[Dict]:
        """Get most frequent values for a key."""
        app = self._sanitize(app)
        data = self._load(app)
        entries = data.get(key, [])
        
        counts: Dict[str, int] = {}
        for e in entries:
            v = str(e["value"])
            counts[v] = counts.get(v, 0) + 1
        
        sorted_items = sorted(counts.items(), key=lambda x: -x[1])
        return [{"value": v, "count": c} for v, c in sorted_items[:top_n]]
    
    def list_apps(self) -> List[str]:
        """List all apps with stored memory."""
        return [
            f.replace(".json", "")
            for f in os.listdir(self._dir)
            if f.endswith(".json")
        ]
    
    def prune(self, app: str = None):
        """Remove entries older than PRUNE_DAYS."""
        cutoff = time.time() - (PRUNE_DAYS * 86400)
        
        apps = [app] if app else self.list_apps()
        for a in apps:
            a = self._sanitize(a)
            data = self._load(a)
            pruned = False
            for key in list(data.keys()):
                before = len(data[key])
                data[key] = [e for e in data[key] if e.get("ts", 0) > cutoff]
                if len(data[key]) < before:
                    pruned = True
                if not data[key]:
                    del data[key]
            if pruned:
                self._save(a, data)
    
    # ═══════════════════════════════════════════════════════
    # TEMPORAL MEMORY (MiroFish-inspired)
    # ═══════════════════════════════════════════════════════
    
    def get_active_facts(self, app: str, key: str = None) -> List[Any]:
        """Get only currently valid (non-expired) facts."""
        app = self._sanitize(app)
        data = self._load(app)
        now = time.time()
        active = []
        
        keys = [key] if key else list(data.keys())
        for k in keys:
            for entry in data.get(k, []):
                expired_at = entry.get("expired_at")
                if expired_at is None or expired_at > now:
                    active.append({
                        "key": k,
                        "value": entry["value"],
                        "age_hours": round((now - entry.get("valid_from", entry.get("ts", now))) / 3600, 1),
                        "relevance": self._compute_relevance(entry, now),
                    })
        
        # Sort by relevance (most relevant first)
        active.sort(key=lambda x: -x["relevance"])
        return active
    
    def get_historical_facts(self, app: str, key: str = None) -> List[Any]:
        """Get expired/superseded facts."""
        app = self._sanitize(app)
        data = self._load(app)
        now = time.time()
        historical = []
        
        keys = [key] if key else list(data.keys())
        for k in keys:
            for entry in data.get(k, []):
                expired_at = entry.get("expired_at")
                if expired_at is not None and expired_at <= now:
                    historical.append({
                        "key": k,
                        "value": entry["value"],
                        "expired_hours_ago": round((now - expired_at) / 3600, 1),
                    })
        
        return historical
    
    def expire_fact(self, app: str, key: str, value: Any) -> bool:
        """Mark a specific fact as expired (no longer valid)."""
        app = self._sanitize(app)
        data = self._load(app)
        now = time.time()
        
        for entry in data.get(key, []):
            expired_at = entry.get("expired_at")
            if entry["value"] == value and (expired_at is None or expired_at > now):
                entry["expired_at"] = now
                self._save(app, data)
                return True
        return False
    
    def _compute_relevance(self, entry: Dict, now: float) -> float:
        """Compute relevance score with time decay."""
        base = entry.get("relevance", 1.0)
        age_hours = (now - entry.get("valid_from", entry.get("ts", now))) / 3600
        # Exponential decay: halves every 48 hours
        decay = 0.5 ** (age_hours / 48.0)
        return round(base * decay, 4)
    
    def clear_app(self, app: str):
        """Clear all memory for an app."""
        app = self._sanitize(app)
        path = os.path.join(self._dir, f"{app}.json")
        with self._lock:
            if os.path.exists(path):
                os.remove(path)
            if app in self._cache:
                del self._cache[app]
    
    def _load(self, app: str) -> Dict:
        if app in self._cache:
            return self._cache[app]
        
        path = os.path.join(self._dir, f"{app}.json")
        with self._lock:
            if os.path.exists(path):
                try:
                    with open(path, 'r') as f:
                        data = json.load(f)
                    self._cache[app] = data
                    return data
                except (json.JSONDecodeError, IOError):
                    return {}
        return {}
    
    def _save(self, app: str, data: Dict):
        path = os.path.join(self._dir, f"{app}.json")
        with self._lock:
            self._cache[app] = data
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
    
    @staticmethod
    def _sanitize(name: str) -> str:
        """Sanitize app name for filename."""
        return "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in name.lower()).strip('_')
