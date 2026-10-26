"""Best-effort transactional notifications through Resend and Meta WhatsApp Cloud API."""

import logging
from html import escape
from datetime import datetime, timezone
from decimal import Decimal

import httpx

from app.settings import settings

logger = logging.getLogger(__name__)


def email_provider_enabled() -> bool:
    return bool(settings.resend_api_key and settings.email_from)


def whatsapp_provider_enabled() -> bool:
    return bool(settings.whatsapp_access_token and settings.whatsapp_phone_number_id
                and settings.whatsapp_api_version)


def _send_email(to: str, *, name: str, amount: Decimal, method: str,
                received_at: datetime, payment_id: str) -> bool:
    if not email_provider_enabled():
        return False
    amount_text = f"₹{amount:,.2f}"
    received_text = received_at.astimezone(timezone.utc).strftime("%d %b %Y, %I:%M %p UTC")
    subject = f"Payment receipt {payment_id[:8]} — {amount_text}"
    html = (
        "<div style=\"font-family:Arial,sans-serif;max-width:560px;margin:auto;color:#20212a\">"
        f"<h2>Payment received</h2><p>Hello {escape(name)},</p>"
        f"<p>We recorded your payment of <strong>{amount_text}</strong>.</p>"
        f"<p>Method: {method.replace('_', ' ').title()}<br>Received: {received_text}</p>"
        f"<p>Receipt reference: {payment_id}</p><p>Thank you.</p></div>"
    )
    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={"from": settings.email_from, "to": [to], "subject": subject, "html": html},
            timeout=8.0,
        )
        response.raise_for_status()
        return True
    except (httpx.HTTPError, ValueError):
        logger.warning("Email delivery failed for payment_id=%s", payment_id)
        return False


def _send_whatsapp(to: str, *, name: str, amount: Decimal, method: str,
                   received_at: datetime, payment_id: str) -> bool:
    if not whatsapp_provider_enabled():
        return False
    # The approved Meta template must have four body placeholders in this order:
    # tenant name, amount, method, received timestamp. Template names and language
    # are configurable because Meta requires the exact approved template locale.
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to.lstrip("+"),
        "type": "template",
        "template": {
            "name": settings.whatsapp_payment_template,
            "language": {"code": settings.whatsapp_template_language},
            "components": [{"type": "body", "parameters": [
                {"type": "text", "text": name[:100]},
                {"type": "text", "text": f"INR {amount:,.2f}"},
                {"type": "text", "text": method.replace("_", " ").title()},
                {"type": "text", "text": received_at.astimezone(timezone.utc).strftime("%d %b %Y %H:%M UTC")},
            ]}],
        },
    }
    url = (f"https://graph.facebook.com/{settings.whatsapp_api_version}/"
           f"{settings.whatsapp_phone_number_id}/messages")
    try:
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {settings.whatsapp_access_token}"},
            json=payload,
            timeout=8.0,
        )
        response.raise_for_status()
        return True
    except (httpx.HTTPError, ValueError):
        logger.warning("WhatsApp delivery failed for payment_id=%s", payment_id)
        return False


def send_payment_receipt(*, email: str | None, whatsapp_phone: str | None,
                         name: str, amount: Decimal, method: str,
                         received_at: datetime, payment_id: str) -> dict[str, bool]:
    """Send only to channels with recorded tenant consent; never raise into ledger flow."""
    sent = {"email": False, "whatsapp": False}
    if email:
        sent["email"] = _send_email(email, name=name, amount=amount, method=method,
                                    received_at=received_at, payment_id=payment_id)
    if whatsapp_phone:
        sent["whatsapp"] = _send_whatsapp(whatsapp_phone, name=name, amount=amount, method=method,
                                          received_at=received_at, payment_id=payment_id)
    return sent
