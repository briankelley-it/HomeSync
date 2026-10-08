"""Bill business logic shared by the web views and the REST API."""

from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.households.services import log_activity

from .models import Bill, BillStatus, Frequency, RecurringBill
from .recurrence import PER_MONTH, occurrences


@transaction.atomic
def save_bill(*, bill: Bill, actor) -> Bill:
    """Create or update a bill, keeping its paid status consistent with payments."""
    from apps.payments.services import refresh_bill_totals

    creating = bill.pk is None
    if creating:
        bill.created_by = actor
    bill.save()
    if not creating:
        # Editing the amount due can turn a paid bill into a partial one (or vice versa).
        refresh_bill_totals(Bill.objects.select_for_update().get(pk=bill.pk))
        bill.refresh_from_db()
    verb = "added" if creating else "updated"
    log_activity(bill.household, actor, verb, f"{actor.display_name} {verb} bill {bill.name}")
    return bill


@transaction.atomic
def delete_bill(*, bill: Bill, actor) -> None:
    if bill.payments.exists():
        raise ValidationError(
            "This bill has recorded payments. Remove the payments first to keep "
            "your payment history accurate."
        )
    log_activity(bill.household, actor, "deleted", f"{actor.display_name} deleted bill {bill.name}")
    bill.delete()


# --------------------------------------------------------------------------- #
# Recurring schedules
# --------------------------------------------------------------------------- #
# On a schedule's first run, include an occurrence that fell due within this
# window so a bill due a few days ago is not silently skipped.
LOOKBACK = timedelta(days=31)
CENT = Decimal("0.01")
SCHEDULE_FIELDS = (
    "name",
    "payee",
    "amount",
    "frequency",
    "start_date",
    "end_date",
    "category_id",
    "property_id",
    "is_active",
)


@transaction.atomic
def generate_bills(schedule: RecurringBill, today: date | None = None) -> int:
    """Create upcoming bills for one schedule. Returns how many were created.

    Idempotent: occurrences up to ``generated_through`` are never revisited
    (so deleted/skipped bills stay deleted), the schedule row is locked while
    generating, and the ``unique_recurring_occurrence`` constraint is a final
    guard against duplicates.
    """
    today = today or timezone.localdate()
    schedule = RecurringBill.objects.select_for_update().get(pk=schedule.pk)
    if not schedule.is_active:
        return 0

    horizon_end = today + settings.RECURRING_BILL_HORIZON
    if schedule.generated_through:
        window_start = schedule.generated_through + timedelta(days=1)
    else:
        window_start = max(schedule.start_date, today - LOOKBACK)
    if window_start > horizon_end:
        return 0

    due_dates = list(
        occurrences(
            schedule.start_date,
            schedule.frequency,
            window_start=window_start,
            window_end=horizon_end,
            end_date=schedule.end_date,
        )
    )
    existing = set(schedule.bills.filter(due_date__in=due_dates).values_list("due_date", flat=True))
    new_bills = [
        Bill(
            household_id=schedule.household_id,
            property_id=schedule.property_id,
            category_id=schedule.category_id,
            recurring=schedule,
            name=schedule.name,
            payee=schedule.payee,
            amount_due=schedule.amount,
            due_date=due,
            created_by=schedule.created_by,
        )
        for due in due_dates
        if due not in existing
    ]
    Bill.objects.bulk_create(new_bills, ignore_conflicts=True)
    schedule.generated_through = horizon_end
    schedule.save(update_fields=["generated_through", "updated_at"])
    return len(new_bills)


def generate_all_recurring_bills(today: date | None = None) -> int:
    """Run generation for every active schedule (used by the Celery beat job)."""
    total = 0
    for schedule in RecurringBill.objects.filter(is_active=True).only("pk"):
        total += generate_bills(schedule, today)
    return total


def _remove_untouched_future_bills(schedule: RecurringBill, today: date) -> None:
    """Delete future bills of a schedule that have no payments yet."""
    schedule.bills.filter(
        due_date__gte=today, status=BillStatus.UNPAID, payments__isnull=True
    ).delete()


@transaction.atomic
def save_recurring_bill(*, schedule: RecurringBill, actor, today: date | None = None) -> int:
    """Create or update a schedule and (re)generate its upcoming bills.

    When the terms of an existing schedule change, future bills nobody has paid
    yet are replaced so they reflect the new amount/date. Paid history is kept.
    """
    today = today or timezone.localdate()
    creating = schedule.pk is None
    changed = False
    if creating:
        schedule.created_by = actor
    else:
        old = RecurringBill.objects.select_for_update().get(pk=schedule.pk)
        changed = any(getattr(old, f) != getattr(schedule, f) for f in SCHEDULE_FIELDS)
    schedule.save()

    if changed:
        _remove_untouched_future_bills(schedule, today)
        schedule.generated_through = today - timedelta(days=1)
        schedule.save(update_fields=["generated_through", "updated_at"])

    created = generate_bills(schedule, today)
    verb = "added" if creating else "updated"
    log_activity(
        schedule.household,
        actor,
        verb,
        f"{actor.display_name} {verb} recurring bill {schedule.name}",
    )
    return created


@transaction.atomic
def delete_recurring_bill(*, schedule: RecurringBill, actor, today: date | None = None) -> None:
    """Stop a schedule: drop its unpaid future bills, keep past ones as history."""
    today = today or timezone.localdate()
    _remove_untouched_future_bills(schedule, today)
    log_activity(
        schedule.household,
        actor,
        "deleted",
        f"{actor.display_name} deleted recurring bill {schedule.name}",
    )
    schedule.delete()


def monthly_recurring_total(household) -> Decimal:
    """Average monthly cost of all active schedules."""
    total = Decimal("0")
    for schedule in RecurringBill.objects.filter(household=household, is_active=True):
        total += schedule.amount * PER_MONTH[Frequency(schedule.frequency)]
    return total.quantize(CENT)
