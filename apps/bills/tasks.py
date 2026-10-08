import logging
from datetime import date

from celery import shared_task

from . import services

logger = logging.getLogger(__name__)


@shared_task
def generate_recurring_bills(today: str | None = None) -> int:
    """Daily job: materialize upcoming bills for every active recurring schedule.

    Safe to run any number of times (see ``services.generate_bills``).
    """
    created = services.generate_all_recurring_bills(date.fromisoformat(today) if today else None)
    logger.info("Generated %s recurring bill(s)", created)
    return created
