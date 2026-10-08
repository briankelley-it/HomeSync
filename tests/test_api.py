from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bills.models import Bill, Category, RecurringBill
from apps.households.models import Role
from apps.payments.models import Payment

from .factories import BillFactory, CategoryFactory, PaymentFactory, PropertyFactory

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


@pytest.fixture
def api(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def api_for():
    def _make(user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    return _make


def url(household, path=""):
    return f"/api/v1/households/{household.pk}/{path}"


class TestAuthAndIsolation:
    def test_anonymous_rejected(self, household):
        assert APIClient().get(url(household, "bills/")).status_code == 403

    def test_household_list_only_shows_mine(self, api, household, other_household):
        data = api.get("/api/v1/households/").json()["results"]
        assert [h["id"] for h in data] == [household.pk]
        assert data[0]["role"] == "owner"

    def test_foreign_household_is_404(self, api, other_household):
        BillFactory(household=other_household)
        assert api.get(url(other_household, "bills/")).status_code == 404
        assert api.get(url(other_household, "summary/")).status_code == 404

    def test_cannot_reach_foreign_bill_through_own_household(self, api, household, other_household):
        foreign = BillFactory(household=other_household)
        assert api.get(url(household, f"bills/{foreign.pk}/")).status_code == 404

    def test_viewer_is_read_only(self, api_for, make_member, household):
        client = api_for(make_member(Role.VIEWER).user)
        assert client.get(url(household, "bills/")).status_code == 200
        response = client.post(url(household, "bills/"), {"name": "x"}, format="json")
        assert response.status_code == 403

    def test_member_cannot_manage_properties(self, api_for, make_member, household):
        client = api_for(make_member(Role.MEMBER).user)
        response = client.post(url(household, "properties/"), {"name": "Cabin"}, format="json")
        assert response.status_code == 403


class TestBillsAPI:
    def payload(self, **overrides):
        data = {
            "name": "Internet",
            "category": Category.objects.get(name="Internet").pk,
            "amount_due": "59.99",
            "due_date": TODAY.isoformat(),
        }
        data.update(overrides)
        return data

    def test_create_and_read_bill(self, api, household):
        response = api.post(url(household, "bills/"), self.payload(), format="json")
        assert response.status_code == 201, response.json()
        body = response.json()
        assert body["amount_due"] == "59.99"  # decimals are strings, never floats
        assert body["status"] == "unpaid"
        assert Bill.objects.get(pk=body["id"]).household == household

    def test_server_controlled_fields_are_ignored(self, api, household):
        response = api.post(
            url(household, "bills/"),
            self.payload(status="paid", amount_paid="59.99"),
            format="json",
        )
        bill = Bill.objects.get(pk=response.json()["id"])
        assert bill.status == "unpaid" and bill.amount_paid == Decimal("0")

    def test_rejects_foreign_category_and_property(self, api, household, other_household):
        foreign_cat = CategoryFactory(household=other_household)
        foreign_prop = PropertyFactory(household=other_household)
        response = api.post(
            url(household, "bills/"),
            self.payload(category=foreign_cat.pk, property=foreign_prop.pk),
            format="json",
        )
        assert response.status_code == 400
        assert {"category", "property"} <= set(response.json())

    def test_filters(self, api, household):
        BillFactory(household=household, name="Late", due_date=TODAY - timedelta(days=1))
        BillFactory(household=household, name="Later", due_date=TODAY + timedelta(days=30))
        names = lambda r: [b["name"] for b in r.json()["results"]]  # noqa: E731
        assert names(api.get(url(household, "bills/"), {"status": "overdue"})) == ["Late"]
        assert names(api.get(url(household, "bills/"), {"search": "later"})) == ["Later"]
        bad = api.get(url(household, "bills/"), {"due_after": "yesterday"})
        assert bad.status_code == 400

    def test_record_partial_then_full_payment(self, api, household):
        bill = BillFactory(household=household, amount_due=Decimal("100.00"))
        endpoint = url(household, f"bills/{bill.pk}/payments/")
        first = api.post(endpoint, {"amount": "40.00", "paid_on": TODAY.isoformat()}, format="json")
        assert first.status_code == 201
        assert api.get(url(household, f"bills/{bill.pk}/")).json()["status"] == "partial"
        api.post(endpoint, {"amount": "60.00", "paid_on": TODAY.isoformat()}, format="json")
        detail = api.get(url(household, f"bills/{bill.pk}/")).json()
        assert detail["status"] == "paid" and detail["balance"] == "0.00"
        assert len(api.get(endpoint).json()) == 2

    def test_overpayment_is_400(self, api, household):
        bill = BillFactory(household=household, amount_due=Decimal("10"))
        response = api.post(
            url(household, f"bills/{bill.pk}/payments/"),
            {"amount": "10.01", "paid_on": TODAY.isoformat()},
            format="json",
        )
        assert response.status_code == 400
        assert "amount" in response.json()

    def test_delete_bill_with_payment_is_400(self, api, household):
        bill = BillFactory(household=household)
        PaymentFactory(bill=bill)
        assert api.delete(url(household, f"bills/{bill.pk}/")).status_code == 400

    def test_delete_payment_reopens_bill(self, api, household, user):
        bill = BillFactory(household=household, amount_due=Decimal("25"))
        api.post(
            url(household, f"bills/{bill.pk}/payments/"),
            {"amount": "25", "paid_on": TODAY.isoformat()},
            format="json",
        )
        payment = Payment.objects.get()
        assert api.delete(url(household, f"payments/{payment.pk}/")).status_code == 204
        bill.refresh_from_db()
        assert bill.status == "unpaid"


class TestOtherResources:
    def test_recurring_bill_generates_bills(self, api, household):
        response = api.post(
            url(household, "recurring-bills/"),
            {
                "name": "Rent",
                "category": Category.objects.get(name="Rent").pk,
                "amount": "1200.00",
                "frequency": "monthly",
                "start_date": TODAY.isoformat(),
            },
            format="json",
        )
        assert response.status_code == 201, response.json()
        schedule = RecurringBill.objects.get(pk=response.json()["id"])
        assert schedule.bills.exists()

    def test_categories_include_builtins_but_only_custom_are_writable(self, api, household):
        names = {c["name"] for c in api.get(url(household, "categories/")).json()["results"]}
        assert "Rent" in names
        rent = Category.objects.get(name="Rent")
        assert api.delete(url(household, f"categories/{rent.pk}/")).status_code == 404
        created = api.post(url(household, "categories/"), {"name": "Pets"}, format="json")
        assert created.status_code == 201
        duplicate = api.post(url(household, "categories/"), {"name": "rent"}, format="json")
        assert duplicate.status_code == 400

    def test_property_members_scoped(self, api, household, other_household):
        foreign_member = other_household.memberships.first()
        response = api.post(
            url(household, "properties/"),
            {"name": "Cabin", "members": [foreign_member.pk]},
            format="json",
        )
        assert response.status_code == 400

    def test_income_and_summary(self, api, household):
        api.post(
            url(household, "income-sources/"),
            {"name": "Salary", "amount": "2000.00", "frequency": "biweekly"},
            format="json",
        )
        BillFactory(household=household, amount_due=Decimal("300"), due_date=TODAY)
        summary = api.get(url(household, "summary/")).json()
        assert summary["income"] == "4333.33"
        assert summary["bills_this_month"] == "300.00"
        assert summary["currency"] == "USD"

    def test_expense_create_sets_household_and_user(self, api, household, user):
        response = api.post(
            url(household, "expenses/"),
            {
                "description": "Paint",
                "amount": "42.00",
                "spent_on": TODAY.isoformat(),
                "category": Category.objects.get(name="Maintenance").pk,
            },
            format="json",
        )
        assert response.status_code == 201
        expense = household.expenses.get()
        assert expense.recorded_by == user

    def test_session_auth_enforces_csrf(self, client, user, household):
        csrf_client = APIClient(enforce_csrf_checks=True)
        csrf_client.force_login(user)
        response = csrf_client.post(url(household, "categories/"), {"name": "X"}, format="json")
        assert response.status_code == 403
