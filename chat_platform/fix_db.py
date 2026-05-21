import sqlite3

conn = sqlite3.connect('c:\\Users\\abdul rahaman\\OneDrive\\Ai software\\software-brain\\chat_platform\\data\\securechat.db')
c = conn.cursor()

queries = [
    'ALTER TABLE users ADD COLUMN is_public INTEGER DEFAULT 0',
    'ALTER TABLE users ADD COLUMN status_text TEXT DEFAULT "Available"',
    'ALTER TABLE users ADD COLUMN custom_theme TEXT DEFAULT "default"',
    'ALTER TABLE users ADD COLUMN bio TEXT DEFAULT ""',
    'ALTER TABLE messages ADD COLUMN message_type TEXT DEFAULT "text"',
    'ALTER TABLE messages ADD COLUMN is_private INTEGER DEFAULT 0',
    'ALTER TABLE messages ADD COLUMN is_read INTEGER DEFAULT 0'
]

for q in queries:
    try:
        c.execute(q)
        print("Success:", q)
    except sqlite3.OperationalError as e:
        print("Skipped:", q, "->", e)

conn.commit()
conn.close()
