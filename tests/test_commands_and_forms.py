from decimal import Decimal

import pytest
from django.core.management import CommandError, call_command

from apps.accounts.models import User
from apps.bills.models import Bill, Category
from apps.budgets.forms import BudgetForm, ExpenseForm, IncomeSourceForm
from apps.budgets.models import Budget
from apps.core.money import format_money

from .factories import HouseholdFactory, PropertyFactory

pytestmark = pytest.mark.django_db


class TestSeedDemo:
    def test_refuses_outside_debug(self, settings, monkeypatch):
        settings.DEBUG = False
        monkeypatch.setenv("DEMO_USER_PASSWORD", "x-demo-password-123")
        with pytest.raises(CommandError, match="DEBUG"):
            call_command("seed_demo")

    def test_requires_password(self, settings, monkeypatch):
        settings.DEBUG = True
        monkeypatch.delenv("DEMO_USER_PASSWORD", raising=False)
        with pytest.raises(CommandError, match="DEMO_USER_PASSWORD"):
            call_command("seed_demo")

    def test_creates_consistent_demo_ledger(self, settings, monkeypatch):
        settings.DEBUG = True
        monkeypatch.setenv("DEMO_USER_PASSWORD", "x-demo-password-123")
        call_command("seed_demo")
        user = User.objects.get(email="demo@houseledger.test")
        household = user.memberships.get().household
        bills = Bill.objects.filter(household=household)
        assert bills.filter(status="paid").exists()
        # Every bill's stored totals agree with its recorded payments.
        for bill in bills.prefetch_related("payments"):
            assert bill.amount_paid == sum((p.amount for p in bill.payments.all()), Decimal(0))
        with pytest.raises(CommandError, match="already exists"):
            call_command("seed_demo")
        call_command("seed_demo", reset=True)  # reset recreates cleanly
        assert User.objects.filter(email="demo@houseledger.test").count() == 1


class TestBudgetForms:
    def test_duplicate_budget_rejected(self, household):
        groceries = Category.objects.get(name="Groceries")
        Budget.objects.create(household=household, category=groceries, amount=Decimal("100"))
        form = BudgetForm(data={"category": groceries.pk, "amount": "50"}, household=household)
        assert not form.is_valid()

    def test_same_category_allowed_per_property(self, household):
        groceries = Category.objects.get(name="Groceries")
        Budget.objects.create(household=household, category=groceries, amount=Decimal("100"))
        cabin = PropertyFactory(household=household)
        form = BudgetForm(
            data={"category": groceries.pk, "property": cabin.pk, "amount": "50"},
            household=household,
        )
        assert form.is_valid(), form.errors

    def test_income_earner_limited_to_household(self, household, owner):
        outsider = HouseholdFactory().memberships.create(user=owner.user, role="owner")
        form = IncomeSourceForm(household=household)
        assert owner in form.fields["earner"].queryset
        assert outsider not in form.fields["earner"].queryset

    def test_expense_defaults_to_today(self, household):
        assert ExpenseForm(household=household).initial["spent_on"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [(Decimal("1234.5"), "$1,234.50"), (Decimal("-3"), "-$3.00"), (None, "$0.00"), ("x", "")],
)
def test_format_money(value, expected):
    assert format_money(value) == expected


def test_format_money_uses_household_currency():
    assert format_money(Decimal("5"), HouseholdFactory.build(currency="EUR")) == "€5.00"
