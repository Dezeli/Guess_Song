import secrets
import string

from .models import Room

ROOM_CODE_ALPHABET = string.ascii_uppercase + string.digits


def generate_room_code(length: int = 6) -> str:
    while True:
        code = "".join(secrets.choice(ROOM_CODE_ALPHABET) for _ in range(length))
        if not Room.objects.filter(code=code).exists():
            return code


def generate_token(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"
