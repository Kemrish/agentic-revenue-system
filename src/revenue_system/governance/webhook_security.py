import hashlib
import hmac
import re


def verify_hmac(body: bytes, signature: str | None, secret: str) -> bool:
    if not signature or not secret:
        return False
    signature = signature.removeprefix("sha256=")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", signature):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.lower())

