from django.db import models
from django.urls import reverse

from apps.core.models import TimeStampedModel
from apps.households.models import Household, Membership


class Property(TimeStampedModel):
    """A home or unit the household pays bills for (primary home, rental, cabin, ...)."""

    class Type(models.TextChoices):
        HOUSE = "house", "House"
        APARTMENT = "apartment", "Apartment"
        CONDO = "condo", "Condo"
        TOWNHOUSE = "townhouse", "Townhouse"
        VACATION = "vacation", "Vacation home"
        RENTAL = "rental", "Rental property"
        OTHER = "other", "Other"

    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="properties")
    name = models.CharField(max_length=120)
    property_type = models.CharField(max_length=20, choices=Type.choices, default=Type.HOUSE)
    address_line1 = models.CharField("Address", max_length=200, blank=True)
    address_line2 = models.CharField("Address line 2", max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField("State / region", max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    is_primary = models.BooleanField("Primary residence", default=False)
    members = models.ManyToManyField(
        Membership,
        blank=True,
        related_name="properties",
        help_text="Household members responsible for this property.",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-is_primary", "name"]
        verbose_name_plural = "properties"
        constraints = [
            models.UniqueConstraint(fields=["household", "name"], name="unique_property_name")
        ]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("properties:detail", args=[self.pk])

    @property
    def address(self) -> str:
        parts = [self.address_line1, self.address_line2, self.city, self.state, self.postal_code]
        return ", ".join(p for p in parts if p)
