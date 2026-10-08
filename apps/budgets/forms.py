from django import forms
from django.utils import timezone

from apps.bills.forms import CategoryChoiceMixin
from apps.core.forms import DateInput, HouseholdModelForm

from .models import Budget, Expense, IncomeSource


class BudgetForm(CategoryChoiceMixin, HouseholdModelForm):
    household_scoped_fields = ("property",)

    class Meta:
        model = Budget
        fields = ("category", "property", "amount")
        labels = {"property": "Property"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._limit_categories()
        self.fields["property"].empty_label = "Whole household"

    def clean(self):
        cleaned = super().clean()
        clash = Budget.objects.filter(
            household=self.household,
            category=cleaned.get("category"),
            property=cleaned.get("property"),
        )
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if cleaned.get("category") and clash.exists():
            raise forms.ValidationError("A budget for this category and property already exists.")
        return cleaned


class IncomeSourceForm(HouseholdModelForm):
    household_scoped_fields = ("earner",)

    class Meta:
        model = IncomeSource
        fields = ("name", "amount", "frequency", "earner", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["earner"].queryset = self.fields["earner"].queryset.select_related("user")
        self.fields["earner"].label_from_instance = lambda m: m.user.display_name


class ExpenseForm(CategoryChoiceMixin, HouseholdModelForm):
    household_scoped_fields = ("property",)

    class Meta:
        model = Expense
        fields = ("description", "amount", "spent_on", "category", "property", "notes")
        widgets = {"spent_on": DateInput(), "notes": forms.Textarea(attrs={"rows": 2})}
        labels = {"property": "Property"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._limit_categories()
        if not self.is_bound and not self.instance.pk:
            self.initial.setdefault("spent_on", timezone.localdate())
