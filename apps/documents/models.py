import builtins
import uuid
from pathlib import Path

from django.conf import settings
from django.db import models
from django.urls import reverse

from apps.bills.models import Bill
from apps.core.models import TimeStampedModel
from apps.households.models import Household
from apps.payments.models import Payment
from apps.properties.models import Property


def document_upload_to(instance: "Document", filename: str) -> str:
    """Store under a random name so user-chosen filenames never reach the filesystem."""
    extension = Path(filename).suffix.lower()
    return f"households/{instance.household_id}/documents/{uuid.uuid4().hex}{extension}"


class Document(TimeStampedModel):
    class Kind(models.TextChoices):
        INVOICE = "invoice", "Invoice / bill"
        RECEIPT = "receipt", "Receipt"
        STATEMENT = "statement", "Statement"
        CONTRACT = "contract", "Contract / lease"
        OTHER = "other", "Other"

    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(max_length=160)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.RECEIPT)
    file = models.FileField(upload_to=document_upload_to, max_length=255)
    original_filename = models.CharField(max_length=255, editable=False)
    content_type = models.CharField(max_length=100, editable=False)
    size = models.PositiveIntegerField(editable=False)
    bill = models.ForeignKey(
        Bill, on_delete=models.SET_NULL, null=True, blank=True, related_name="documents"
    )
    payment = models.ForeignKey(
        Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name="documents"
    )
    property = models.ForeignKey(
        Property, on_delete=models.SET_NULL, null=True, blank=True, related_name="documents"
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("documents:download", args=[self.pk])

    @builtins.property  # the ``property`` FK field shadows the builtin here
    def is_image(self) -> bool:
        return self.content_type.startswith("image/")
