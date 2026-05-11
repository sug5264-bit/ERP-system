"""Multi-channel delivery adapters (SMTP email, Slack webhook).

Each adapter implements the same `.send(subject, body, recipients)` interface.
Activated by environment / config — when not configured, `.send()` is a no-op.
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

import httpx

from app.core.config import settings

log = logging.getLogger("erp.notifications")


class EmailAdapter:
    """SMTP email delivery."""

    def __init__(self) -> None:
        self.host = settings.smtp_host
        self.port = settings.smtp_port
        self.user = settings.smtp_user
        self.password = settings.smtp_password
        self.from_addr = settings.smtp_from
        self.use_tls = settings.smtp_use_tls

    def is_configured(self) -> bool:
        return bool(self.host)

    def send(self, subject: str, body: str, recipients: list[str]) -> bool:
        if not self.is_configured() or not recipients:
            return False
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = self.from_addr
            msg["To"] = ", ".join(recipients)
            msg.set_content(body)
            with smtplib.SMTP(self.host, self.port, timeout=10) as s:
                if self.use_tls:
                    s.starttls()
                if self.user and self.password:
                    s.login(self.user, self.password)
                s.send_message(msg)
            return True
        except Exception:
            log.exception("SMTP send failed (host=%s)", self.host)
            return False


class SlackAdapter:
    """Slack incoming-webhook delivery. Each instance is bound to a webhook URL."""

    def __init__(self, webhook_url: str | None = None) -> None:
        self.webhook_url = webhook_url or getattr(settings, "slack_webhook_url", None)

    def is_configured(self) -> bool:
        return bool(self.webhook_url)

    def send(self, subject: str, body: str, recipients: list[str] | None = None) -> bool:
        if not self.is_configured():
            return False
        text = f"*{subject}*\n{body}"
        try:
            r = httpx.post(self.webhook_url, json={"text": text}, timeout=10.0)
            if r.status_code != 200:
                log.warning("Slack webhook returned %s", r.status_code)
                return False
            return True
        except Exception:
            log.exception("Slack send failed")
            return False
