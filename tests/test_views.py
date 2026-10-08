"""Integration tests for the HTML views: rendering, permissions, and isolation."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.bills.models import Bill, Category, RecurringBill
from apps.budgets.models import Expense
from apps.households.models import Role
from apps.payments.models import Payment

from .factories import BillFactory, PaymentFactory, PropertyFactory, RecurringBillFactory

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()
HTMX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture
def bill(household):
    return BillFactory(household=household, amount_due=Decimal("80.00"), name="Water bill")


PAGES = [
    "core:dashboard",
    "bills:list",
    "bills:calendar",
    "bills:recurring_list",
    "bills:category_list",
    "payments:list",
    "properties:list",
    "budgets:analytics",
    "budgets:budget_list",
    "budgets:expense_list",
    "documents:list",
    "households:members",
]


@pytest.mark.parametrize("name", PAGES)
def test_pages_render_for_viewer(client_for, make_member, bill, name):
    viewer = make_member(Role.VIEWER)
    response = client_for(viewer.user).get(reverse(name))
    assert response.status_code == 200


@pytest.mark.parametrize("name", PAGES)
def test_pages_require_login(client, name):
    response = client.get(reverse(name))
    assert response.status_code == 302
    assert reverse("accounts:login") in response.url


class TestBillViews:
    def test_create_bill(self, auth_client, household):
        response = auth_client.post(
            reverse("bills:create"),
            {
                "name": "Electric",
                "category": Category.objects.get(name="Electricity").pk,
                "amount_due": "140.25",
                "due_date": TODAY.isoformat(),
            },
        )
        bill = Bill.objects.get(name="Electric")
        assert response.status_code == 302
        assert bill.household == household
        assert bill.amount_due == Decimal("140.25")

    def test_htmx_create_returns_modal_then_hx_redirect(self, auth_client):
        response = auth_client.get(reverse("bills:create"), **HTMX)
        assert b"modal-title" in response.content
        response = auth_client.post(
            reverse("bills:create"),
            {
                "name": "Gas",
                "category": Category.objects.get(name="Gas").pk,
                "amount_due": "30",
                "due_date": TODAY.isoformat(),
            },
            **HTMX,
        )
        assert response.status_code == 204
        assert response["HX-Redirect"].startswith("/bills/")

    def test_invalid_htmx_post_rerenders_form(self, auth_client):
        response = auth_client.post(reverse("bills:create"), {"name": ""}, **HTMX)
        assert response.status_code == 200
        assert b"This field is required" in response.content

    def test_viewer_cannot_create_or_delete(self, client_for, make_member, bill):
        client = client_for(make_member(Role.VIEWER).user)
        assert client.get(reverse("bills:create")).status_code == 403
        assert client.post(reverse("bills:delete", args=[bill.pk])).status_code == 403
        assert Bill.objects.filter(pk=bill.pk).exists()

    def test_other_household_bill_is_404(self, auth_client, other_household):
        foreign = BillFactory(household=other_household)
        for name in ("bills:detail", "bills:update", "bills:delete"):
            assert auth_client.get(reverse(name, args=[foreign.pk])).status_code == 404
        assert auth_client.post(reverse("bills:delete", args=[foreign.pk])).status_code == 404
        assert Bill.objects.filter(pk=foreign.pk).exists()

    def test_delete_bill_with_payments_is_blocked(self, auth_client, bill):
        PaymentFactory(bill=bill, amount=Decimal("10"))
        response = auth_client.post(reverse("bills:delete", args=[bill.pk]), follow=True)
        assert Bill.objects.filter(pk=bill.pk).exists()
        assert "recorded payments" in response.content.decode()

    def test_status_filter_and_search(self, auth_client, household, bill):
        BillFactory(household=household, name="Old", due_date=TODAY - timedelta(days=3))
        response = auth_client.get(reverse("bills:list"), {"status": "overdue"})
        assert [b.name for b in response.context["object_list"]] == ["Old"]
        response = auth_client.get(reverse("bills:list"), {"status": "all", "q": "water"})
        assert [b.name for b in response.context["object_list"]] == ["Water bill"]

    def test_htmx_filter_returns_table_partial(self, auth_client, bill):
        response = auth_client.get(reverse("bills:list"), HTTP_HX_TARGET="bill-table", **HTMX)
        templates = [t.name for t in response.templates]
        assert "bills/partials/bill_table.html" in templates
        assert "layouts/app.html" not in templates

    def test_calendar_month_navigation(self, auth_client, household):
        BillFactory(
            household=household, name="Jan rent", due_date=TODAY.replace(year=2030, month=1, day=5)
        )
        response = auth_client.get(reverse("bills:calendar"), {"year": 2030, "month": 1})
        assert response.context["month"].month == 1
        assert response.context["month_count"] == 1
        assert b"Jan rent" in response.content
        # Garbage input falls back to the current month instead of erroring.
        assert auth_client.get(reverse("bills:calendar"), {"year": "x"}).status_code == 200


class TestPaymentViews:
    def test_record_payment(self, auth_client, bill):
        response = auth_client.post(
            reverse("payments:record", args=[bill.pk]),
            {"amount": "80.00", "paid_on": TODAY.isoformat(), "method": "card"},
        )
        assert response.status_code == 302
        bill.refresh_from_db()
        assert bill.status == "paid"

    def test_overpayment_shows_error(self, auth_client, bill):
        response = auth_client.post(
            reverse("payments:record", args=[bill.pk]),
            {"amount": "999", "paid_on": TODAY.isoformat(), "method": "card"},
        )
        assert response.status_code == 200
        assert not Payment.objects.exists()

    def test_cannot_pay_other_household_bill(self, auth_client, other_household):
        foreign = BillFactory(household=other_household)
        response = auth_client.post(
            reverse("payments:record", args=[foreign.pk]),
            {"amount": "1", "paid_on": TODAY.isoformat(), "method": "card"},
        )
        assert response.status_code == 404

    def test_viewer_cannot_record_payment(self, client_for, make_member, bill):
        client = client_for(make_member(Role.VIEWER).user)
        response = client.post(
            reverse("payments:record", args=[bill.pk]),
            {"amount": "1", "paid_on": TODAY.isoformat(), "method": "card"},
        )
        assert response.status_code == 403

    def test_delete_payment(self, auth_client, bill):
        payment = PaymentFactory(bill=bill, amount=Decimal("80"))
        auth_client.post(reverse("payments:delete", args=[payment.pk]))
        assert not Payment.objects.filter(pk=payment.pk).exists()

    def test_csv_export_is_scoped_and_injection_safe(self, auth_client, household, other_household):
        mine = BillFactory(household=household, name="=HYPERLINK(evil)")
        PaymentFactory(bill=mine, amount=Decimal("12.50"))
        PaymentFactory(bill=BillFactory(household=other_household, name="Not mine"))
        content = auth_client.get(reverse("payments:export")).content.decode()
        assert "'=HYPERLINK(evil)" in content
        assert "12.50" in content
        assert "Not mine" not in content


class TestRecurringViews:
    def test_create_schedule_generates_bills(self, auth_client, household):
        response = auth_client.post(
            reverse("bills:recurring_create"),
            {
                "name": "Rent",
                "category": Category.objects.get(name="Rent").pk,
                "amount": "1500",
                "frequency": "monthly",
                "start_date": TODAY.isoformat(),
                "is_active": "on",
            },
        )
        assert response.status_code == 302
        schedule = RecurringBill.objects.get(name="Rent")
        assert schedule.bills.count() >= 2  # today + next month within the 60-day horizon

    def test_delete_schedule_keeps_paid_history(self, auth_client, household, user):
        schedule = RecurringBillFactory(household=household, start_date=TODAY - timedelta(days=5))
        from apps.bills.services import generate_bills

        generate_bills(schedule, TODAY)
        past = schedule.bills.order_by("due_date").first()
        PaymentFactory(bill=past, amount=past.amount_due)
        auth_client.post(reverse("bills:recurring_delete", args=[schedule.pk]))
        assert not RecurringBill.objects.filter(pk=schedule.pk).exists()
        assert Bill.objects.filter(pk=past.pk).exists()  # paid history kept


class TestCategoryAndPropertyViews:
    def test_member_cannot_create_category(self, client_for, make_member):
        client = client_for(make_member(Role.MEMBER).user)
        assert client.get(reverse("bills:category_create")).status_code == 403

    def test_builtin_category_cannot_be_edited(self, auth_client):
        rent = Category.objects.get(name="Rent")
        assert auth_client.get(reverse("bills:category_update", args=[rent.pk])).status_code == 404

    def test_category_in_use_cannot_be_deleted(self, auth_client, household):
        custom = Category.objects.create(household=household, name="Pets")
        BillFactory(household=household, category=custom)
        auth_client.post(reverse("bills:category_delete", args=[custom.pk]))
        assert Category.objects.filter(pk=custom.pk).exists()

    def test_only_one_primary_property(self, auth_client, household):
        first = PropertyFactory(household=household, is_primary=True)
        auth_client.post(
            reverse("properties:create"),
            {"name": "New home", "property_type": "house", "is_primary": "on"},
        )
        first.refresh_from_db()
        assert not first.is_primary
        assert household.properties.get(name="New home").is_primary

    def test_property_detail_scoped(self, auth_client, other_household):
        foreign = PropertyFactory(household=other_household)
        assert auth_client.get(reverse("properties:detail", args=[foreign.pk])).status_code == 404


class TestBudgetViews:
    def test_member_can_record_expense(self, client_for, make_member, household):
        client = client_for(make_member(Role.MEMBER).user)
        response = client.post(
            reverse("budgets:expense_create"),
            {
                "description": "Groceries",
                "amount": "45.10",
                "spent_on": TODAY.isoformat(),
                "category": Category.objects.get(name="Groceries").pk,
            },
        )
        assert response.status_code == 302
        expense = Expense.objects.get()
        assert expense.household == household and expense.amount == Decimal("45.10")

    def test_member_cannot_manage_budgets(self, client_for, make_member):
        client = client_for(make_member(Role.MEMBER).user)
        assert client.get(reverse("budgets:budget_create")).status_code == 403
        assert client.get(reverse("budgets:income_create")).status_code == 403


class TestHouseholdDeletion:
    def test_owner_can_delete_household_with_history(self, auth_client, household, bill, user):
        PaymentFactory(bill=bill, amount=Decimal("5"))
        auth_client.post(reverse("households:delete"), {"confirm_name": household.name})
        assert not type(household).objects.filter(pk=household.pk).exists()
        assert not Payment.objects.exists()

    def test_wrong_confirmation_name_keeps_household(self, auth_client, household):
        auth_client.post(reverse("households:delete"), {"confirm_name": "nope"})
        assert type(household).objects.filter(pk=household.pk).exists()

    def test_admin_cannot_delete_household(self, client_for, make_member, household):
        client = client_for(make_member(Role.ADMIN).user)
        response = client.post(reverse("households:delete"), {"confirm_name": household.name})
        assert response.status_code == 403


@pytest.mark.parametrize("evil", ["https://evil.example/", "javascript:alert(1)", "//evil.example"])
def test_next_parameter_cannot_point_off_site(auth_client, evil):
    response = auth_client.get(reverse("bills:create"), {"next": evil})
    assert response.context["cancel_url"] == reverse("bills:list")


def test_next_parameter_allows_local_path(auth_client):
    response = auth_client.get(reverse("bills:create"), {"next": "/bills/calendar/"})
    assert response.context["cancel_url"] == "/bills/calendar/"
