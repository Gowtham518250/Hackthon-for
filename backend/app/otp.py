import hashlib
import secrets
from datetime import datetime, timezone, timedelta


OTP_EXPIRE_MINUTES = 10
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_SECONDS = 60


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def new_otp() -> str:
    return f"{secrets.randbelow(900000) + 100000:06d}"


def hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.strip().encode("utf-8")).hexdigest()


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
