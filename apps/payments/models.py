from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.bills.models import Bill
from apps.core.models import MoneyField, TimeStampedModel
from apps.households.models import Household


class PaymentMethod(models.TextChoices):
    BANK_TRANSFER = "bank_transfer", "Bank transfer"
    CARD = "card", "Credit / debit card"
    AUTOPAY = "autopay", "Autopay"
    CHECK = "check", "Check"
    CASH = "cash", "Cash"
    OTHER = "other", "Other"


class Payment(TimeStampedModel):
    """A payment a household member *recorded* against a bill.

    HouseLedger never moves money; a payment row only exists because a user
    entered it. Bills with payments cannot be deleted (``PROTECT``) so the
    payment history is never silently lost.
    """

    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="payments")
    bill = models.ForeignKey(Bill, on_delete=models.PROTECT, related_name="payments")
    amount = MoneyField(validators=[MinValueValidator(Decimal("0.01"))])
    paid_on = models.DateField()
    method = models.CharField(
        max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.BANK_TRANSFER
    )
    reference = models.CharField(
        "Confirmation #",
        max_length=80,
        blank=True,
        help_text="Optional confirmation code. Never enter card or account numbers.",
    )
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )

    class Meta:
        ordering = ["-paid_on", "-created_at"]
        indexes = [models.Index(fields=["household", "paid_on"])]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="payment_amount_positive")
        ]

    def __str__(self) -> str:
        return f"{self.amount} for {self.bill.name} on {self.paid_on}"
