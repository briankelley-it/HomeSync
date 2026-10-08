"""Payment recording.

These functions are the only code allowed to change a bill's ``amount_paid``
and ``status``. Each runs in a transaction and locks the bill row with
``SELECT ... FOR UPDATE`` so two people recording payments at the same time
cannot both pay off the same balance.
"""

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

from apps.bills.models import Bill, BillStatus
from apps.core.money import format_money
from apps.households.services import log_activity

from .models import Payment

ZERO = Decimal("0.00")


def refresh_bill_totals(bill: Bill) -> Bill:
    """Recalculate ``amount_paid``, ``status``, and ``paid_on`` from payments."""
    totals = bill.payments.aggregate(total=Sum("amount"), last=Max("paid_on"))
    paid = totals["total"] or ZERO
    if paid >= bill.amount_due:
        status, paid_on = BillStatus.PAID, totals["last"]
    elif paid > ZERO:
        status, paid_on = BillStatus.PARTIAL, None
    else:
        status, paid_on = BillStatus.UNPAID, None
    bill.amount_paid, bill.status, bill.paid_on = paid, status, paid_on
    bill.save(update_fields=["amount_paid", "status", "paid_on", "updated_at"])
    return bill


@transaction.atomic
def record_payment(
    *,
    bill: Bill,
    amount: Decimal,
    paid_on: date,
    recorded_by,
    method: str = "bank_transfer",
    reference: str = "",
    notes: str = "",
) -> Payment:
    bill = Bill.objects.select_for_update().get(pk=bill.pk)
    amount = Decimal(amount)
    if amount <= ZERO:
        raise ValidationError({"amount": "Payment amount must be greater than zero."})
    if amount > bill.balance:
        raise ValidationError(
            {"amount": f"Payment exceeds the remaining balance of {bill.balance}."}
        )
    if paid_on > timezone.localdate():
        raise ValidationError({"paid_on": "Payment date cannot be in the future."})

    payment = Payment.objects.create(
        household=bill.household,
        bill=bill,
        amount=amount,
        paid_on=paid_on,
        method=method,
        reference=reference,
        notes=notes,
        recorded_by=recorded_by,
    )
    refresh_bill_totals(bill)
    kind = "payment" if bill.status == BillStatus.PAID else "partial payment"
    log_activity(
        bill.household,
        recorded_by,
        "paid",
        f"{recorded_by.display_name} recorded a {kind} of "
        f"{format_money(amount, bill.household)} for {bill.name}",
    )
    return payment


@transaction.atomic
def delete_payment(*, payment: Payment, actor) -> Bill:
    bill = Bill.objects.select_for_update().get(pk=payment.bill_id)
    amount = payment.amount
    payment.delete()
    refresh_bill_totals(bill)
    log_activity(
        bill.household,
        actor,
        "unpaid",
        f"{actor.display_name} removed a payment of "
        f"{format_money(amount, bill.household)} from {bill.name}",
    )
    return bill


def outstanding_total(household) -> Decimal:
    """Total still owed across all open bills."""
    totals = (
        Bill.objects.filter(household=household)
        .open()
        .aggregate(due=Sum("amount_due"), paid=Sum("amount_paid"))
    )
    return (totals["due"] or ZERO) - (totals["paid"] or ZERO)
