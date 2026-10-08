from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.bills.models import Category
from apps.core.models import MoneyField, TimeStampedModel
from apps.households.models import Household, Membership
from apps.properties.models import Property

POSITIVE = [MinValueValidator(Decimal("0.01"))]
CENT = Decimal("0.01")


class IncomeSource(TimeStampedModel):
    """Expected household income, normalized to a monthly figure for budgeting."""

    class Frequency(models.TextChoices):
        WEEKLY = "weekly", "Weekly"
        BIWEEKLY = "biweekly", "Every two weeks"
        SEMIMONTHLY = "semimonthly", "Twice a month"
        MONTHLY = "monthly", "Monthly"
        ANNUAL = "annual", "Annually"

    # Multiplier converting one payment into its average monthly equivalent.
    MONTHLY_FACTOR = {
        Frequency.WEEKLY: Decimal(52) / Decimal(12),
        Frequency.BIWEEKLY: Decimal(26) / Decimal(12),
        Frequency.SEMIMONTHLY: Decimal(2),
        Frequency.MONTHLY: Decimal(1),
        Frequency.ANNUAL: Decimal(1) / Decimal(12),
    }

    household = models.ForeignKey(
        Household, on_delete=models.CASCADE, related_name="income_sources"
    )
    name = models.CharField(
        max_length=120, help_text="For example: Salary, Freelance, Rent received"
    )
    amount = MoneyField(validators=POSITIVE, help_text="Amount per payment, after tax.")
    frequency = models.CharField(
        max_length=12, choices=Frequency.choices, default=Frequency.MONTHLY
    )
    earner = models.ForeignKey(
        Membership, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="income_amount_positive")
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def monthly_amount(self) -> Decimal:
        factor = self.MONTHLY_FACTOR[self.Frequency(self.frequency)]
        return (self.amount * factor).quantize(CENT, rounding=ROUND_HALF_UP)


class Budget(TimeStampedModel):
    """A monthly spending limit for a category (optionally for one property)."""

    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="budgets")
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="+")
    property = models.ForeignKey(
        Property, on_delete=models.CASCADE, null=True, blank=True, related_name="budgets"
    )
    amount = MoneyField("Monthly limit", validators=POSITIVE)

    class Meta:
        ordering = ["category__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["household", "category", "property"],
                name="unique_budget_per_property",
            ),
            models.UniqueConstraint(
                fields=["household", "category"],
                condition=Q(property__isnull=True),
                name="unique_household_wide_budget",
            ),
            models.CheckConstraint(condition=Q(amount__gt=0), name="budget_amount_positive"),
        ]

    def __str__(self) -> str:
        scope = f" · {self.property}" if self.property_id else ""
        return f"{self.category}{scope}: {self.amount}/month"


class Expense(TimeStampedModel):
    """A one-off household expense that is not a bill (groceries, repairs, ...)."""

    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="expenses")
    property = models.ForeignKey(
        Property, on_delete=models.SET_NULL, null=True, blank=True, related_name="expenses"
    )
    category = models.ForeignKey(Category, on_delete=models.RESTRICT, related_name="expenses")
    description = models.CharField(max_length=160)
    amount = MoneyField(validators=POSITIVE)
    spent_on = models.DateField()
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )

    class Meta:
        ordering = ["-spent_on", "-created_at"]
        indexes = [models.Index(fields=["household", "spent_on"])]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="expense_amount_positive")
        ]

    def __str__(self) -> str:
        return f"{self.description} ({self.amount})"
