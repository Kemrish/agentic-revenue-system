import hashlib
import hmac

from revenue_system.governance.webhook_security import verify_hmac


def test_hmac_signature_is_verified():
    body = b'{"eventId":"1"}'
    signature = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert verify_hmac(body, signature, "secret") is True
    assert verify_hmac(body, "bad", "secret") is False

