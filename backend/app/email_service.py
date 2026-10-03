import logging
import httpx

from .config import settings

logger = logging.getLogger("deepsearch.email")


def _brevo_enabled() -> bool:
    return (
        settings.email_provider == "brevo"
        and bool(settings.brevo_api_key)
        and bool(settings.brevo_sender_email)
    )


def send_email(recipient: str, subject: str, text: str) -> bool:
    """Retail Mind-compatible HTTPS transactional email using Brevo."""
    if not _brevo_enabled():
        logger.error(
            "Email provider is not configured. Set EMAIL_PROVIDER=brevo, "
            "BREVO_API_KEY and BREVO_SENDER_EMAIL."
        )
        return False

    payload = {
        "sender": {
            "email": settings.brevo_sender_email,
            "name": settings.brevo_sender_name,
        },
        "to": [{"email": recipient}],
        "subject": subject,
        "textContent": text,
    }

    try:
        response = httpx.post(
            settings.brevo_api_url,
            headers={
                "accept": "application/json",
                "api-key": settings.brevo_api_key,
                "content-type": "application/json",
            },
            json=payload,
            timeout=settings.email_timeout_seconds,
        )
        if 200 <= response.status_code < 300:
            return True

        logger.error(
            "Brevo email failed status=%s body=%s",
            response.status_code,
            response.text[:500],
        )
        return False
    except Exception:
        logger.exception("Brevo email request failed")
        return False


def otp_email(otp: str, purpose: str) -> tuple[str, str]:
    subject = f"{otp} is your DeepSearch {purpose} OTP"
    body = (
        f"Your DeepSearch one-time password for {purpose} is:\n\n"
        f"{otp}\n\n"
        "This OTP is valid for 10 minutes. Do not share it with anyone.\n\n"
        "DeepSearch"
    )
    return subject, body
