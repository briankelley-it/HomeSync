from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.bills.forms import BillForm, CategoryForm, RecurringBillForm
from apps.bills.models import Bill, BillStatus, Category
from apps.properties.forms import PropertyForm

from .factories import (
    BillFactory,
    CategoryFactory,
    HouseholdFactory,
    PropertyFactory,
    RecurringBillFactory,
)

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


class TestCategories:
    def test_defaults_are_seeded(self):
        names = set(Category.objects.filter(household=None).values_list("name", flat=True))
        assert {"Rent", "Mortgage", "Electricity", "Internet", "Water", "Gas"} <= names
        assert {"Insurance", "Subscriptions"} <= names

    def test_for_household_includes_builtin_and_own_only(self, household, other_household):
        mine = CategoryFactory(household=household, name="Pet care")
        theirs = CategoryFactory(household=other_household, name="Boat")
        visible = Category.objects.for_household(household)
        assert mine in visible
        assert theirs not in visible
        assert visible.filter(name="Rent").exists()

    def test_category_form_rejects_builtin_name(self, household):
        form = CategoryForm(data={"name": "rent", "color": "#059669"}, household=household)
        assert not form.is_valid()
        assert "name" in form.errors


class TestBillModel:
    def test_money_is_decimal(self, household):
        bill = BillFactory(household=household, amount_due=Decimal("10.10"))
        bill.refresh_from_db()
        assert isinstance(bill.amount_due, Decimal)
        assert bill.balance == Decimal("10.10")

    @pytest.mark.parametrize(
        ("offset", "status", "expected"),
        [
            (-1, BillStatus.UNPAID, "overdue"),
            (-1, BillStatus.PARTIAL, "overdue"),
            (3, BillStatus.UNPAID, "due_soon"),
            (30, BillStatus.UNPAID, "unpaid"),
            (30, BillStatus.PARTIAL, "partial"),
            (-10, BillStatus.PAID, "paid"),
        ],
    )
    def test_display_status(self, household, offset, status, expected):
        bill = BillFactory.build(
            household=household, due_date=TODAY + timedelta(days=offset), status=status
        )
        assert bill.display_status(TODAY) == expected

    def test_queryset_helpers(self, household):
        overdue = BillFactory(household=household, due_date=TODAY - timedelta(days=2))
        soon = BillFactory(household=household, due_date=TODAY + timedelta(days=2))
        later = BillFactory(household=household, due_date=TODAY + timedelta(days=40))
        paid = BillFactory(
            household=household, due_date=TODAY - timedelta(days=2), status=BillStatus.PAID
        )
        assert list(Bill.objects.overdue(TODAY)) == [overdue]
        assert list(Bill.objects.due_soon(TODAY)) == [soon]
        assert later in Bill.objects.open() and paid not in Bill.objects.open()

    def test_amount_must_be_positive_at_db_level(self, household):
        with pytest.raises(IntegrityError), transaction.atomic():
            BillFactory(household=household, amount_due=Decimal("0"))

    def test_recurring_occurrence_is_unique(self, household):
        schedule = RecurringBillFactory(household=household)
        BillFactory(household=household, recurring=schedule, due_date=TODAY)
        with pytest.raises(IntegrityError), transaction.atomic():
            BillFactory(household=household, recurring=schedule, due_date=TODAY)

    def test_recurring_end_date_check_constraint(self, household):
        with pytest.raises(IntegrityError), transaction.atomic():
            RecurringBillFactory(household=household, end_date=TODAY - timedelta(days=1))


class TestHouseholdScopedForms:
    def _bill_data(self, **overrides):
        data = {
            "name": "Power",
            "category": Category.objects.get(name="Electricity").pk,
            "amount_due": "120.50",
            "due_date": TODAY.isoformat(),
        }
        data.update(overrides)
        return data

    def test_bill_form_rejects_foreign_property(self, household, other_household):
        foreign = PropertyFactory(household=other_household)
        form = BillForm(data=self._bill_data(property=foreign.pk), household=household)
        assert not form.is_valid()
        assert "property" in form.errors

    def test_bill_form_rejects_foreign_category(self, household, other_household):
        foreign = CategoryFactory(household=other_household)
        form = BillForm(data=self._bill_data(category=foreign.pk), household=household)
        assert not form.is_valid()
        assert "category" in form.errors

    def test_bill_form_rejects_non_positive_amount(self, household):
        form = BillForm(data=self._bill_data(amount_due="0"), household=household)
        assert not form.is_valid()

    def test_bill_form_cannot_go_below_amount_paid(self, household):
        bill = BillFactory(household=household, amount_paid=Decimal("50"))
        form = BillForm(data=self._bill_data(amount_due="40"), instance=bill, household=household)
        assert not form.is_valid()
        assert "amount_due" in form.errors

    def test_recurring_form_validates_dates(self, household):
        form = RecurringBillForm(
            data={
                "name": "Internet",
                "category": Category.objects.get(name="Internet").pk,
                "amount": "60",
                "frequency": "monthly",
                "start_date": TODAY.isoformat(),
                "end_date": (TODAY - timedelta(days=1)).isoformat(),
                "is_active": True,
            },
            household=household,
        )
        assert not form.is_valid()
        assert "end_date" in form.errors

    def test_property_form_members_limited_to_household(self, household, make_member):
        mine = make_member()
        foreign = HouseholdFactory().memberships.create(user=make_member().user, role="member")
        form = PropertyForm(household=household)
        queryset = form.fields["members"].queryset
        assert mine in queryset and foreign not in queryset

    def test_property_name_unique_per_household(self, household):
        PropertyFactory(household=household, name="Main House")
        form = PropertyForm(
            data={"name": "main house", "property_type": "house"}, household=household
        )
        assert not form.is_valid()
