import hashlib
import hmac
import secrets

PREFIX = "nx_live_"


def generate_key() -> tuple[str, str, bytes, str]:
    """Returns (secret, display_prefix, hash, last4). The secret is shown once and never stored."""
    secret = PREFIX + secrets.token_urlsafe(32)
    return secret, secret[: len(PREFIX) + 4], hash_key(secret), secret[-4:]


def hash_key(secret: str) -> bytes:
    return hashlib.sha256(secret.encode()).digest()


def verify_hash(secret: str, stored: bytes) -> bool:
    return hmac.compare_digest(hash_key(secret), stored)
