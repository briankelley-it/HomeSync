"""Bill business logic shared by the web views and the REST API."""

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.households.services import log_activity

from .models import Bill


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
