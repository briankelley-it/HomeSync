import logging
from datetime import date
from smtplib import SMTPException

from celery import shared_task
from django.core.mail import send_mail

from . import services

logger = logging.getLogger(__name__)


@shared_task(
    autoretry_for=(SMTPException, ConnectionError),
    retry_backoff=True,
    max_retries=3,
)
def send_bill_reminders(today: str | None = None) -> int:
    """Daily job: email due-soon and overdue reminders. ``today`` is ISO for testing."""
    sent = services.send_bill_reminders(date.fromisoformat(today) if today else None)
    logger.info("Sent %s bill reminder email(s)", sent)
    return sent


@shared_task(
    autoretry_for=(SMTPException, ConnectionError),
    retry_backoff=True,
    max_retries=5,
)
def send_email(subject: str, body: str, recipients: list[str]) -> None:
    """Send a plain-text email outside the request/response cycle."""
    from django.conf import settings

    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, recipients)
