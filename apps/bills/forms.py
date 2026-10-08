from django import forms
from django.db.models import Q

from apps.core.forms import DateInput, HouseholdModelForm

from .models import Bill, Category, RecurringBill


class CategoryChoiceMixin:
    """Limit the category dropdown to built-ins plus this household's categories."""

    def _limit_categories(self):
        self.fields["category"].queryset = Category.objects.for_household(self.household)


class BillForm(CategoryChoiceMixin, HouseholdModelForm):
    household_scoped_fields = ("property",)

    class Meta:
        model = Bill
        fields = ("name", "payee", "category", "property", "amount_due", "due_date", "notes")
        widgets = {"due_date": DateInput(), "notes": forms.Textarea(attrs={"rows": 3})}
        labels = {"amount_due": "Amount due", "property": "Property"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._limit_categories()
        self.fields["amount_due"].widget.attrs.update({"step": "0.01", "min": "0.01"})

    def clean_amount_due(self):
        amount = self.cleaned_data["amount_due"]
        if self.instance.pk and amount < self.instance.amount_paid:
            raise forms.ValidationError(
                f"Amount due cannot be less than the {self.instance.amount_paid} already paid."
            )
        return amount


class RecurringBillForm(CategoryChoiceMixin, HouseholdModelForm):
    household_scoped_fields = ("property",)

    class Meta:
        model = RecurringBill
        fields = (
            "name",
            "payee",
            "category",
            "property",
            "amount",
            "frequency",
            "start_date",
            "end_date",
            "is_active",
            "autopay",
            "notes",
        )
        widgets = {
            "start_date": DateInput(),
            "end_date": DateInput(),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {"property": "Property", "start_date": "First due date"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._limit_categories()
        self.fields["amount"].widget.attrs.update({"step": "0.01", "min": "0.01"})


class CategoryForm(HouseholdModelForm):
    class Meta:
        model = Category
        fields = ("name", "color")

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        clash = Category.objects.filter(
            Q(household=self.household) | Q(household__isnull=True), name__iexact=name
        )
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError("A category with this name already exists.")
        return name
