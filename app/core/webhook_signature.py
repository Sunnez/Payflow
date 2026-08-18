import hashlib
import hmac


def generate_webhook_signature(
    secret: str,
    payload: bytes,
) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()


def verify_webhook_signature(
    secret: str,
    payload: bytes,
    signature: str,
) -> bool:
    expected = generate_webhook_signature(
        secret,
        payload,
    )

    return hmac.compare_digest(
        expected,
        signature,
    )
