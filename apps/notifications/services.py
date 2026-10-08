"""Bill reminder selection and delivery.

Run daily by Celery beat (``apps.notifications.tasks.send_bill_reminders``).
Each (bill, user, kind) reminder is sent at most once thanks to ``ReminderLog``
and its unique constraint. Reminders describe what is *due*; they never claim
a bill was paid.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.bills.models import Bill

from .models import NotificationPreference, ReminderLog

LOOKAHEAD = timedelta(days=30)  # the largest allowed ``remind_days_before``
OVERDUE_WINDOW = timedelta(days=14)  # don't alert about long-stale bills
DEFAULT_PREFERENCE = NotificationPreference(
    email_reminders=True, remind_days_before=3, overdue_alerts=True
)


@dataclass(frozen=True)
class Reminder:
    bill: Bill
    kind: str


def recipients_for(bill: Bill) -> list:
    """Members assigned to the bill's property, or every household member."""
    if bill.property_id:
        assigned = [m.user for m in bill.property.members.all()]
        if assigned:
            return [u for u in assigned if u.is_active]
    return [m.user for m in bill.household.memberships.all() if m.user.is_active]


def reminder_kind(bill: Bill, preference: NotificationPreference, today: date) -> str | None:
    if bill.due_date < today:
        return ReminderLog.Kind.OVERDUE if preference.overdue_alerts else None
    if preference.email_reminders and (bill.due_date - today).days <= preference.remind_days_before:
        return ReminderLog.Kind.DUE_SOON
    return None


def collect_reminders(today: date) -> dict[tuple, list[Reminder]]:
    """Return pending reminders grouped by ``(user, household)``."""
    bills = list(
        Bill.objects.open()
        .filter(due_date__range=(today - OVERDUE_WINDOW, today + LOOKAHEAD))
        .select_related("household", "category", "property")
        .prefetch_related("household__memberships__user", "property__members__user")
        .order_by("due_date")
    )
    already_sent = set(
        ReminderLog.objects.filter(bill__in=bills).values_list("bill_id", "user_id", "kind")
    )
    preferences = {
        p.user_id: p
        for p in NotificationPreference.objects.filter(
            user__memberships__household__in={b.household_id for b in bills}
        )
    }

    grouped: dict[tuple, list[Reminder]] = defaultdict(list)
    for bill in bills:
        for user in recipients_for(bill):
            kind = reminder_kind(bill, preferences.get(user.pk, DEFAULT_PREFERENCE), today)
            if kind and (bill.pk, user.pk, kind) not in already_sent:
                grouped[(user, bill.household)].append(Reminder(bill, kind))
    return grouped


def send_reminder_email(user, household, reminders: list[Reminder], today: date) -> None:
    overdue = [r.bill for r in reminders if r.kind == ReminderLog.Kind.OVERDUE]
    upcoming = [r.bill for r in reminders if r.kind == ReminderLog.Kind.DUE_SOON]
    context = {
        "user": user,
        "household": household,
        "overdue": overdue,
        "upcoming": upcoming,
        "today": today,
        "site_url": settings.SITE_URL.rstrip("/"),
    }
    count = len(reminders)
    subject = f"{household.name}: {count} bill reminder{'s' if count != 1 else ''}"
    message = EmailMultiAlternatives(
        subject=subject,
        body=render_to_string("notifications/emails/reminder.txt", context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    message.attach_alternative(
        render_to_string("notifications/emails/reminder.html", context), "text/html"
    )
    message.send()


def send_bill_reminders(today: date | None = None) -> int:
    """Send one digest email per (user, household). Returns emails sent.

    The log rows and the email share a transaction: if sending fails, the rows
    roll back and the reminder is retried on the next run.
    """
    today = today or timezone.localdate()
    sent = 0
    for (user, household), reminders in collect_reminders(today).items():
        with transaction.atomic():
            ReminderLog.objects.bulk_create(
                [ReminderLog(bill=r.bill, user=user, kind=r.kind) for r in reminders],
                ignore_conflicts=True,
            )
            send_reminder_email(user, household, reminders, today)
        sent += 1
    return sent
