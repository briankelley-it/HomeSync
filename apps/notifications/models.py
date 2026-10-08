from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.bills.models import Bill
from apps.core.models import TimeStampedModel


class NotificationPreference(TimeStampedModel):
    """Per-user email reminder settings (apply to every household the user is in)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_preference"
    )
    email_reminders = models.BooleanField("Email me before bills are due", default=True)
    remind_days_before = models.PositiveSmallIntegerField(
        "Days before the due date",
        default=3,
        validators=[MinValueValidator(0), MaxValueValidator(30)],
        help_text="0 sends the reminder on the due date itself.",
    )
    overdue_alerts = models.BooleanField("Email me when a bill becomes overdue", default=True)

    def __str__(self) -> str:
        return f"Notification preferences for {self.user}"

    @classmethod
    def for_user(cls, user) -> "NotificationPreference":
        preference, _ = cls.objects.get_or_create(user=user)
        return preference


class ReminderLog(models.Model):
    """Records that a reminder was sent, so each one goes out at most once."""

    class Kind(models.TextChoices):
        DUE_SOON = "due_soon", "Due soon"
        OVERDUE = "overdue", "Overdue"

    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name="reminders")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sent_at"]
        constraints = [
            models.UniqueConstraint(fields=["bill", "user", "kind"], name="unique_reminder")
        ]

    def __str__(self) -> str:
        return f"{self.kind} reminder for {self.bill} to {self.user}"
