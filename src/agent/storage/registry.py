"""
registry.py

Handles idempotency. Tracks processed files/emails to prevent duplicate work.
"""
import os
import json
import hashlib
from typing import Dict, Any, List
from ...config import config

class ProcessedRegistry:
    def __init__(self):
        self.path = config.paths.get("registry", "./data/processed_registry.json")
        self._data = self._load()

    def _load(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []

    def _save(self):
        # Ensure dir exists
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self._data, f, indent=2)

    def is_processed(self, email_id: str, attachment_name: str) -> bool:
        """Checks if this specific attachment from this email was processed."""
        for entry in self._data:
            if entry.get("email_id") == email_id and entry.get("attachment_name") == attachment_name:
                return True
        return False

    def mark_processed(self, email_id: str, attachment_name: str, file_path: str = None):
        """Marks an item as processed."""
        entry = {
            "email_id": email_id,
            "attachment_name": attachment_name,
            "timestamp": _get_timestamp(),
            "file_hash": _compute_hash(file_path) if file_path else None
        }
        self._data.append(entry)
        self._save()

def _get_timestamp():
    import time
    return time.strftime("%Y-%m-%d %H:%M:%S")

def _compute_hash(file_path: str) -> str:
    if not file_path or not os.path.exists(file_path):
        return None
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read in chunks
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()
