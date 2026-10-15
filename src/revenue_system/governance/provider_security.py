"""Native webhook signature schemes; never trust proxy/Host headers for signing URLs."""

import base64
import hashlib
import hmac
import re
import time


def fresh(timestamp, scale: int = 1, tolerance: int = 300) -> bool:
    try:
        return abs(time.time() - int(timestamp) / scale) <= tolerance
    except (ValueError, TypeError, OverflowError):
        return False


def hubspot_valid(raw: bytes, signature: str, timestamp: str, secret: str, url: str) -> bool:
    if not secret or not url or not fresh(timestamp, 1000):
        return False
    # HubSpot specifies a limited URI decoding set, NOT full unquote().
    chars = {"3A": ":", "2F": "/", "3F": "?", "40": "@", "21": "!", "24": "$", "27": "'",
             "28": "(", "29": ")", "2A": "*", "2C": ",", "3B": ";"}
    url = re.sub(r"%([0-9a-fA-F]{2})", lambda m: chars.get(m[1].upper(), m[0]), url)
    signed = b"POST" + url.encode() + raw + timestamp.encode()
    expected = base64.b64encode(hmac.digest(secret.encode(), signed, "sha256")).decode()
    return hmac.compare_digest(expected, signature)


def resend_valid(raw: bytes, message_id: str, timestamp: str, signature: str, secret: str) -> bool:
    if not secret or not message_id or not fresh(timestamp):
        return False
    try:
        key = base64.b64decode(secret.removeprefix("whsec_"), validate=True)
    except ValueError:
        return False
    expected = base64.b64encode(hmac.digest(key, message_id.encode() + b"." + timestamp.encode() + b"." + raw, "sha256")).decode()
    return any(hmac.compare_digest(candidate, f"v1,{expected}") for candidate in signature.split())


def dropbox_valid(body: dict, secret: str) -> bool:
    event = body.get("event") or {}
    if not secret or not isinstance(event, dict):
        return False
    # Provider retries can arrive later; event IDs plus verified remote state
    # prevent duplicate advancement. Do not reject legitimate delayed callbacks.
    value = str(event.get("event_time", "")) + str(event.get("event_type", ""))
    expected = hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, str(event.get("event_hash", "")))


def reply_token(action_id: str, secret: str) -> str:
    if not secret:
        raise ValueError("MAIL_THREAD_SECRET must be configured for reply correlation")
    return hmac.new(secret.encode(), action_id.encode(), hashlib.sha256).hexdigest()[:40]
