"""
email.py

The 'Communication' organ of the Agent.
Handles Inbox -> Process -> Outbox workflow.
Supports multiple backends (Mock, IMAP/SMTP, Gmail API).
"""
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from ..tool import Tool

class EmailTool(Tool):
    name = "email_communication"
    description = "Manage emails. Commands: read_unread, download_attachments, send_email."
    
    def __init__(self, backend_type: str = "mock", credentials: Dict = {}):
        self.backend_type = backend_type
        if backend_type == "mock":
            self.backend = _MockBackend()
        elif backend_type == "imap":
            self.backend = _ImapSmtpBackend(credentials)
        else:
            self.backend = _MockBackend() # Fallback
            
    def run(self, action: str, **kwargs) -> Any:
        """
        Execute email action.
        
        Args:
            action: read_unread, download_attachments, send_email
            kwargs: Parameters for the action
        """
        if action == "read_unread":
            return self.backend.read_unread(**kwargs)
            
        elif action == "download_attachments":
            return self.backend.download_attachments(**kwargs)
            
        elif action == "send_email":
            return self.backend.send_email(**kwargs)
            
        elif action == "fetch_and_download":
            # Composite action for MVP Planner
            subject = kwargs.get("subject_filter")
            save_dir = kwargs.get("save_dir", "./downloads")
            
            # 1. Read
            emails = self.backend.read_unread(limit=1, subject_filter=subject)
            if not emails:
                return {"error": "No matching email found"}
            
            target_email = emails[0]
            if not target_email.get("has_attachments"):
                return {"error": "Email found but has no attachments", "email": target_email}
                
            # 2. Download
            return self.backend.download_attachments(email_id=target_email["id"], save_dir=save_dir)
            
        else:
            return f"Error: Unknown email action '{action}'"

class _EmailBackend:
    def read_unread(self, limit: int = 5, subject_filter: str = None) -> List[Dict]:
        pass
        
    def download_attachments(self, email_id: str, save_dir: str) -> Dict[str, List[str]]:
        pass
        
    def send_email(self, to: str, subject: str, body: str, attachments: List[str] = []) -> Dict[str, str]:
        pass

class _MockBackend(_EmailBackend):
    """
    Simulated Inbox for testing/demo.
    """
    def __init__(self):
        self.inbox = [
            {
                "id": "msg_123",
                "sender": "boss@company.com",
                "subject": "Sales Report",
                "date": "2026-02-15 09:00:00",
                "has_attachments": True,
                "attachments": ["sales_data.xlsx"]
            },
            {
                "id": "msg_124",
                "sender": "newsletter@spam.com",
                "subject": "Weekly Update",
                "date": "2026-02-15 10:00:00",
                "has_attachments": False,
                "attachments": []
            }
        ]
        self.sent_box = []
        
    def read_unread(self, limit: int = 5, subject_filter: str = None) -> List[Dict]:
        results = []
        for email in self.inbox:
            if subject_filter:
                if subject_filter.lower() in email["subject"].lower():
                    results.append(email)
            else:
                results.append(email)
            if len(results) >= limit:
                break
        return results
        
    def download_attachments(self, email_id: str, save_dir: str) -> Dict[str, List[str]]:
        # Find email
        email = next((e for e in self.inbox if e["id"] == email_id), None)
        if not email:
            return {"error": "Email not found"}
            
        if not email["has_attachments"]:
            return {"files": []}
            
        # Create Save Dir
        import os
        import pandas as pd
        
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
            
        saved_files = []
        for filename in email["attachments"]:
            path = os.path.join(save_dir, filename)
            
            # Generate Real Mock Data
            if filename.endswith(".xlsx"):
                data = {
                    "Date": ["2026-02-15", "2026-02-15", "2026-02-15"],
                    "Product": ["Widget A", "Widget B", "Widget A"],
                    "Revenue": [1000, 500, 1000],
                    "Region": ["North", "South", "East"]
                }
                df = pd.DataFrame(data)
                df.to_excel(path, index=False)
                saved_files.append(filename)
            else:
                # Text file fallback
                with open(path, "w") as f:
                    f.write("Mock content")
                saved_files.append(filename)
                
        return {
            "files": saved_files, 
            "status": "downloaded_real_file", 
            "path": save_dir,
            "email_id": email_id,
            "source_email": email["sender"]
        }
        
    def send_email(self, to: str, subject: str, body: str, attachments: List[str] = []) -> Dict[str, str]:
        msg_id = f"sent_{int(time.time())}"
        self.sent_box.append({
            "id": msg_id,
            "to": to,
            "subject": subject,
            "body": body, 
            "attachments": attachments
        })
        return {"status": "sent", "message_id": msg_id}

class _ImapSmtpBackend(_EmailBackend):
    """
    Real implementation using imaplib/smtplib.
    Placeholder for Phase S implementation.
    """
    def __init__(self, credentials):
        self.credentials = credentials
        
    def read_unread(self, limit=5, subject_filter=None):
        return [{"error": "IMAP not implemented yet"}]
