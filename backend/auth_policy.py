"""Single-user authorization policy for NOVA."""
from fastapi import HTTPException


UNAUTHORIZED_MESSAGE = (
    "NOVA, Yapay Zeka Sanatçısı Bora ÜNSAL’a özel kişisel asistandır. "
    "Yetkisiz erişim reddedildi."
)
ALLOWED_USER_EMAIL = "yapayzekasanatcisi@gmail.com"
AUTH_SESSION_VERSION = 2


def normalize_email(value) -> str:
    return str(value or "").strip().casefold()


def require_allowed_identity(identity: dict) -> str:
    """Return the canonical email or stop unauthorized identities with 403."""
    email = normalize_email(identity.get("email"))
    verified_claim = identity.get("email_verified")
    explicitly_unverified = verified_claim is False or (
        isinstance(verified_claim, str)
        and verified_claim.strip().casefold() in {"false", "0", "no"}
    )
    if email != ALLOWED_USER_EMAIL or explicitly_unverified:
        raise HTTPException(status_code=403, detail=UNAUTHORIZED_MESSAGE)
    return email