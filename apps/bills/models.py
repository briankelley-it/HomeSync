import builtins
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.urls import reverse
from django.utils import timezone

from apps.core.models import MoneyField, TimeStampedModel
from apps.households.models import Household
from apps.properties.models import Property

DUE_SOON_DAYS = 7
POSITIVE = [MinValueValidator(Decimal("0.01"))]


class CategoryQuerySet(models.QuerySet):
    def for_household(self, household):
        """Built-in categories plus the household's own custom categories."""
        return self.filter(Q(household__isnull=True) | Q(household=household))


class Category(TimeStampedModel):
    """Bill / expense category. ``household=None`` marks a built-in default."""

    COLOR_CHOICES = [
        ("#059669", "Emerald"),
        ("#0284c7", "Sky"),
        ("#7c3aed", "Violet"),
        ("#db2777", "Pink"),
        ("#ea580c", "Orange"),
        ("#ca8a04", "Amber"),
        ("#0d9488", "Teal"),
        ("#4f46e5", "Indigo"),
        ("#dc2626", "Red"),
        ("#64748b", "Slate"),
        ("#16a34a", "Green"),
        ("#94a3b8", "Gray"),
    ]

    household = models.ForeignKey(
        Household, on_delete=models.CASCADE, null=True, blank=True, related_name="categories"
    )
    name = models.CharField(max_length=60)
    color = models.CharField(max_length=7, choices=COLOR_CHOICES, default="#059669")

    objects = CategoryQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"
        constraints = [
            models.UniqueConstraint(fields=["household", "name"], name="unique_household_category"),
            models.UniqueConstraint(
                fields=["name"],
                condition=Q(household__isnull=True),
                name="unique_builtin_category",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_builtin(self) -> bool:
        return self.household_id is None


class Frequency(models.TextChoices):
    WEEKLY = "weekly", "Weekly"
    MONTHLY = "monthly", "Monthly"
    QUARTERLY = "quarterly", "Quarterly"
    ANNUAL = "annual", "Annually"


class RecurringBill(TimeStampedModel):
    """A schedule that materializes upcoming :class:`Bill` rows automatically.

    ``generated_through`` records the last date already processed, so a bill a
    user deletes (for example, a skipped month) is never recreated, while the
    ``unique_recurring_occurrence`` constraint on ``Bill`` guarantees no
    duplicates even if two workers run at once.
    """

    household = models.ForeignKey(
        Household, on_delete=models.CASCADE, related_name="recurring_bills"
    )
    property = models.ForeignKey(
        Property, on_delete=models.SET_NULL, null=True, blank=True, related_name="recurring_bills"
    )
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="+")
    name = models.CharField(max_length=120)
    payee = models.CharField(max_length=120, blank=True)
    amount = MoneyField(validators=POSITIVE)
    frequency = models.CharField(
        max_length=10, choices=Frequency.choices, default=Frequency.MONTHLY
    )
    start_date = models.DateField(help_text="Due date of the first bill.")
    end_date = models.DateField(null=True, blank=True, help_text="Leave blank to repeat forever.")
    is_active = models.BooleanField(default=True)
    autopay = models.BooleanField(
        default=False,
        help_text="For your reference only. Bills are never marked paid automatically.",
    )
    notes = models.TextField(blank=True)
    generated_through = models.DateField(null=True, blank=True, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="recurring_amount_positive"),
            models.CheckConstraint(
                condition=Q(end_date__isnull=True) | Q(end_date__gte=F("start_date")),
                name="recurring_end_after_start",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_frequency_display()})"

    def get_absolute_url(self) -> str:
        return reverse("bills:recurring_detail", args=[self.pk])

    def clean(self):
        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date must be on or after the start date."})


class BillStatus(models.TextChoices):
    UNPAID = "unpaid", "Unpaid"
    PARTIAL = "partial", "Partially paid"
    PAID = "paid", "Paid"


class BillQuerySet(models.QuerySet):
    def open(self):
        return self.exclude(status=BillStatus.PAID)

    def overdue(self, today: date | None = None):
        today = today or timezone.localdate()
        return self.open().filter(due_date__lt=today)

    def due_soon(self, today: date | None = None, days: int = DUE_SOON_DAYS):
        today = today or timezone.localdate()
        return self.open().filter(due_date__gte=today, due_date__lte=today + timedelta(days=days))

    def in_month(self, year: int, month: int):
        return self.filter(due_date__year=year, due_date__month=month)


class Bill(TimeStampedModel):
    """A single amount owed on a due date.

    ``amount_paid`` and ``status`` are derived from recorded ``Payment`` rows
    and are only ever updated by ``apps.payments.services`` inside a
    transaction. A bill is never marked paid unless a user records a payment.
    """

    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="bills")
    property = models.ForeignKey(
        Property, on_delete=models.SET_NULL, null=True, blank=True, related_name="bills"
    )
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="bills")
    recurring = models.ForeignKey(
        RecurringBill, on_delete=models.SET_NULL, null=True, blank=True, related_name="bills"
    )
    name = models.CharField(max_length=120)
    payee = models.CharField(max_length=120, blank=True)
    amount_due = MoneyField(validators=POSITIVE)
    amount_paid = MoneyField(default=Decimal("0.00"), editable=False)
    due_date = models.DateField()
    status = models.CharField(
        max_length=10, choices=BillStatus.choices, default=BillStatus.UNPAID, editable=False
    )
    paid_on = models.DateField(null=True, blank=True, editable=False)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    objects = BillQuerySet.as_manager()

    class Meta:
        ordering = ["due_date", "name"]
        indexes = [
            models.Index(fields=["household", "due_date"]),
            models.Index(fields=["household", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["recurring", "due_date"],
                condition=Q(recurring__isnull=False),
                name="unique_recurring_occurrence",
            ),
            models.CheckConstraint(condition=Q(amount_due__gt=0), name="bill_amount_due_positive"),
            models.CheckConstraint(
                condition=Q(amount_paid__gte=0), name="bill_amount_paid_non_negative"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} due {self.due_date:%Y-%m-%d}"

    def get_absolute_url(self) -> str:
        return reverse("bills:detail", args=[self.pk])

    @builtins.property  # the ``property`` FK field shadows the builtin here
    def balance(self) -> Decimal:
        return max(self.amount_due - self.amount_paid, Decimal("0.00"))

    @builtins.property
    def is_paid(self) -> bool:
        return self.status == BillStatus.PAID

    def display_status(self, today: date | None = None) -> str:
        """Status for UI badges: paid, partial, overdue, due_soon, or unpaid."""
        if self.status == BillStatus.PAID:
            return "paid"
        today = today or timezone.localdate()
        if self.due_date < today:
            return "overdue"
        if self.status == BillStatus.PARTIAL:
            return "partial"
        if self.due_date <= today + timedelta(days=DUE_SOON_DAYS):
            return "due_soon"
        return "unpaid"

    @builtins.property
    def days_until_due(self) -> int:
        return (self.due_date - timezone.localdate()).days
