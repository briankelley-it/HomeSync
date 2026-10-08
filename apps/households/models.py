import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class Role(models.TextChoices):
    VIEWER = "viewer", "Viewer"
    MEMBER = "member", "Member"
    ADMIN = "admin", "Admin"
    OWNER = "owner", "Owner"


# Higher rank = more privileges. Permission checks compare ranks.
ROLE_RANK = {Role.VIEWER: 10, Role.MEMBER: 20, Role.ADMIN: 30, Role.OWNER: 40}


class Household(TimeStampedModel):
    CURRENCY_CHOICES = [
        ("USD", "US Dollar ($)"),
        ("CAD", "Canadian Dollar ($)"),
        ("EUR", "Euro (€)"),
        ("GBP", "British Pound (£)"),
        ("AUD", "Australian Dollar ($)"),
    ]
    CURRENCY_SYMBOLS = {"USD": "$", "CAD": "$", "EUR": "€", "GBP": "£", "AUD": "$"}

    name = models.CharField(max_length=120)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default="USD")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through="Membership", related_name="households"
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @property
    def currency_symbol(self) -> str:
        return self.CURRENCY_SYMBOLS.get(self.currency, "$")


class Membership(TimeStampedModel):
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)

    class Meta:
        ordering = ["household__name", "user__email"]
        constraints = [
            models.UniqueConstraint(fields=["household", "user"], name="unique_household_member")
        ]

    def __str__(self) -> str:
        return f"{self.user} in {self.household} ({self.role})"

    @property
    def rank(self) -> int:
        return ROLE_RANK[Role(self.role)]

    def has_role(self, minimum: str) -> bool:
        return self.rank >= ROLE_RANK[Role(minimum)]

    @property
    def can_edit(self) -> bool:
        """Create/edit bills, payments, expenses, and documents."""
        return self.has_role(Role.MEMBER)

    @property
    def can_manage(self) -> bool:
        """Manage properties, budgets, categories, and members."""
        return self.has_role(Role.ADMIN)

    @property
    def is_owner(self) -> bool:
        return self.role == Role.OWNER


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


class InvitationQuerySet(models.QuerySet):
    def pending(self):
        return self.filter(accepted_at__isnull=True, revoked=False, expires_at__gt=timezone.now())


class Invitation(TimeStampedModel):
    """An emailed invitation to join a household.

    Only a SHA-256 hash of the token is stored, so a database leak does not
    expose usable invitation links.
    """

    VALID_FOR = timedelta(days=7)

    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField()
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked = models.BooleanField(default=False)

    objects = InvitationQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Invitation for {self.email} to {self.household}"

    @classmethod
    def create_with_token(cls, **kwargs) -> tuple["Invitation", str]:
        raw_token = secrets.token_urlsafe(32)
        invitation = cls.objects.create(
            token_hash=_hash_token(raw_token),
            expires_at=timezone.now() + cls.VALID_FOR,
            **kwargs,
        )
        return invitation, raw_token

    @classmethod
    def find_pending(cls, raw_token: str) -> "Invitation | None":
        return cls.objects.pending().filter(token_hash=_hash_token(raw_token)).first()

    @property
    def is_pending(self) -> bool:
        return not self.accepted_at and not self.revoked and self.expires_at > timezone.now()


class ActivityLog(models.Model):
    """Human-readable audit trail shown on the dashboard's recent activity feed."""

    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="activity")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    verb = models.CharField(max_length=40)
    description = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.description
