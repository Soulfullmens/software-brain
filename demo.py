# demo.py
import json

# Pretend we loaded this from an API
user_data = {
    "id": 101,
    "email": "test@example.com"
}

# Mistake: Trying to access a key that doesn't exist
print("User name is:", user_data.get("name", "Unknown"))
print(user_data.get("age", "Age not available"))