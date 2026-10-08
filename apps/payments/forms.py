from django import forms
from django.utils import timezone

from apps.core.forms import DateInput

from .models import Payment


class PaymentForm(forms.ModelForm):
    """Record a full or partial payment against ``bill``.

    Validation here gives friendly form errors; ``services.record_payment``
    repeats the checks under a row lock, which is the authoritative guard.
    """

    class Meta:
        model = Payment
        fields = ("amount", "paid_on", "method", "reference", "notes")
        widgets = {"paid_on": DateInput(), "notes": forms.Textarea(attrs={"rows": 2})}
        labels = {"paid_on": "Paid on"}

    def __init__(self, *args, bill, **kwargs):
        self.bill = bill
        super().__init__(*args, **kwargs)
        self.fields["amount"].widget.attrs.update(
            {"step": "0.01", "min": "0.01", "max": str(bill.balance)}
        )
        if not self.is_bound:
            self.initial.setdefault("amount", bill.balance)
            self.initial.setdefault("paid_on", timezone.localdate())

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount > self.bill.balance:
            raise forms.ValidationError(
                f"That is more than the remaining balance ({self.bill.balance})."
            )
        return amount

    def clean_paid_on(self):
        paid_on = self.cleaned_data["paid_on"]
        if paid_on > timezone.localdate():
            raise forms.ValidationError("Payment date cannot be in the future.")
        return paid_on
