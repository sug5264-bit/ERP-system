"""Lightweight SMTP email service.

If SMTP is not configured, emails are logged to stdout instead of sent —
this keeps PoC environments working without external services.
"""
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger("erp.email")


def send_email(to: str, subject: str, body: str) -> None:
    """Send a plain-text email. Raises on SMTP errors."""
    if not settings.smtp_host:
        logger.warning("SMTP not configured. Would have sent to %s: %s", to, subject)
        print(f"[EMAIL-DEV] To: {to}\nSubject: {subject}\n\n{body}\n---")
        return

    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_user and settings.smtp_password:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)


def send_email_safe(to: str, subject: str, body: str) -> bool:
    """Best-effort email send. Returns True on success, False on failure."""
    try:
        send_email(to, subject, body)
        return True
    except Exception as exc:
        logger.exception("Email send failed: %s", exc)
        return False
