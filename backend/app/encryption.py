"""
Fernet symmetric encryption for secret config values.
The key is loaded once from app.config at module import time.
"""
from cryptography.fernet import Fernet, InvalidToken

from app.config import FERNET_KEY

_fernet = Fernet(FERNET_KEY.encode())


def encrypt(plaintext: str) -> str:
    """Encrypt a plaintext string. Returns a URL-safe base64 Fernet token."""
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """
    Decrypt a Fernet token back to plaintext.
    Raises InvalidToken if the ciphertext is invalid or was encrypted with a different key.
    """
    return _fernet.decrypt(ciphertext.encode()).decode()


def is_encrypted(value: str) -> bool:
    """Best-effort check: Fernet tokens start with 'gAA'."""
    return value.startswith("gAA")
