import bcrypt

def _hash(password: str) -> bytes:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt())

def verify_password(plain: str, hashed: bytes) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed)

# Hardcoded users for v1 — replace with a database before real deployment
USERS = {
    "admin": {"username": "admin", "hashed_password": _hash("admin123"), "role": "admin"},
    "user":  {"username": "user",  "hashed_password": _hash("user123"),  "role": "user"},
    "caleb": {"username": "caleb", "hashed_password": _hash("password"), "role":
  "admin"}
}

def get_user(username: str):
    return USERS.get(username)
