"""
test_email_tool.py

Verify EmailTool functionality (Mock Backend).
"""
from src.agent.tools.email import EmailTool

def main():
    print("+------------------------------------------------------+")
    print("| TESTING EMAIL TOOL (MOCK BACKEND)                    |")
    print("+------------------------------------------------------+")
    
    email = EmailTool(backend_type="mock")
    
    # 1. Read Unread
    print("\n[Test 1] Reading Unread Emails...")
    emails = email.run("read_unread", limit=2)
    print(f"Emails found: {len(emails)}")
    assert len(emails) == 2
    print(emails[0])
    assert emails[0]["subject"] == "Sales Report"
    
    # 2. Download Attachments
    print("\n[Test 2] Downloading Attachments...")
    msg_id = emails[0]["id"]
    result = email.run("download_attachments", email_id=msg_id, save_dir="./downloads")
    print(f"Download Result: {result}")
    assert "sales_data.xlsx" in result["files"]
    
    # 3. Send Email
    print("\n[Test 3] Sending Email...")
    send_result = email.run("send_email", to="manager@corp.com", subject="Analysis", body="Done.")
    print(f"Send Result: {send_result}")
    assert send_result["status"] == "sent"
    assert "message_id" in send_result

    print("\n+------------------------------------------------------+")
    print("| EMAIL TOOL VERIFIED                                  |")
    print("+------------------------------------------------------+")

if __name__ == "__main__":
    main()
