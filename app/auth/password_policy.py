import re

COMMON_PASSWORDS = {
    "password",
    "password123",
    "12345678",
    "qwerty123",
    "admin123",
    "letmein",
}


def validate_password_strength(password: str):
    if len(password) < 12:
        return False, "Password must be at least 12 characters"
    if not re.search(r"[A-Z]", password):
        return False, "Password must include an uppercase letter"
    if not re.search(r"[a-z]", password):
        return False, "Password must include a lowercase letter"
    if not re.search(r"\d", password):
        return False, "Password must include a digit"
    if not re.search(r"[^A-Za-z0-9]", password):
        return False, "Password must include a symbol"
    if password.lower() in COMMON_PASSWORDS:
        return False, "Password is too common"
    return True, None
