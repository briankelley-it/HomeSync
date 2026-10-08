from datetime import date
from decimal import Decimal

import pytest

from apps.bills.models import Category
from apps.budgets import analytics
from apps.budgets.models import Budget, Expense, IncomeSource

from .factories import BillFactory, PaymentFactory, PropertyFactory

pytestmark = pytest.mark.django_db
TODAY = date(2026, 3, 15)


def expense(household, amount, spent_on, category="Groceries", **kwargs):
    return Expense.objects.create(
        household=household,
        category=Category.objects.get(name=category),
        description="x",
        amount=Decimal(amount),
        spent_on=spent_on,
        **kwargs,
    )


class TestIncome:
    @pytest.mark.parametrize(
        ("amount", "frequency", "monthly"),
        [
            ("1000", "monthly", "1000.00"),
            ("1200", "weekly", "5200.00"),
            ("2000", "biweekly", "4333.33"),
            ("1500", "semimonthly", "3000.00"),
            ("60000", "annual", "5000.00"),
        ],
    )
    def test_monthly_amount_is_exact_decimal(self, household, amount, frequency, monthly):
        source = IncomeSource(household=household, amount=Decimal(amount), frequency=frequency)
        assert source.monthly_amount == Decimal(monthly)
        assert isinstance(source.monthly_amount, Decimal)

    def test_inactive_income_excluded(self, household):
        IncomeSource.objects.create(household=household, name="A", amount=Decimal("100"))
        IncomeSource.objects.create(
            household=household, name="B", amount=Decimal("999"), is_active=False
        )
        assert analytics.monthly_income(household) == Decimal("100.00")


class TestSpending:
    def test_month_bounds(self):
        assert analytics.month_bounds(date(2028, 2, 10)) == (date(2028, 2, 1), date(2028, 2, 29))

    def test_trend_combines_payments_and_expenses(self, household):
        bill = BillFactory(household=household, amount_due=Decimal("200"))
        PaymentFactory(bill=bill, amount=Decimal("120.10"), paid_on=date(2026, 2, 3))
        expense(household, "30.05", date(2026, 2, 20))
        expense(household, "10.00", date(2026, 3, 1))
        trend = analytics.spending_trend(household, TODAY, months=3)
        assert [m["label"] for m in trend] == ["Jan 2026", "Feb 2026", "Mar 2026"]
        assert trend[1]["bills"] == Decimal("120.10")
        assert trend[1]["other"] == Decimal("30.05")
        assert trend[1]["total"] == Decimal("150.15")
        assert trend[2]["total"] == Decimal("10.00")
        assert trend[0]["total"] == Decimal("0.00")

    def test_category_breakdown_merges_sources(self, household):
        bill = BillFactory(household=household, category=Category.objects.get(name="Groceries"))
        PaymentFactory(bill=bill, amount=Decimal("5"), paid_on=TODAY)
        expense(household, "7.50", TODAY)
        expense(household, "100", TODAY, category="Maintenance")
        rows = analytics.category_breakdown(household, date(2026, 3, 1), date(2026, 3, 31))
        assert [(r["name"], r["total"]) for r in rows] == [
            ("Maintenance", Decimal("100.00")),
            ("Groceries", Decimal("12.50")),
        ]

    def test_property_filter(self, household):
        cabin = PropertyFactory(household=household)
        expense(household, "40", TODAY, property=cabin)
        expense(household, "60", TODAY)
        start, end = analytics.month_bounds(TODAY)
        assert analytics.spending_between(household, start, end, prop=cabin) == Decimal("40")
        assert analytics.spending_between(household, start, end) == Decimal("100")

    def test_other_households_not_counted(self, household, other_household):
        expense(other_household, "999", TODAY)
        start, end = analytics.month_bounds(TODAY)
        assert analytics.spending_between(household, start, end) == Decimal("0.00")


class TestBudgetsAndSummary:
    def test_budget_progress(self, household):
        Budget.objects.create(
            household=household,
            category=Category.objects.get(name="Groceries"),
            amount=Decimal("100"),
        )
        expense(household, "125", TODAY)
        (row,) = analytics.budget_progress(household, TODAY)
        assert row["spent"] == Decimal("125")
        assert row["remaining"] == Decimal("-25")
        assert row["over"] and row["percent"] == 125

    def test_dashboard_summary(self, household):
        IncomeSource.objects.create(household=household, name="Pay", amount=Decimal("3000"))
        overdue = BillFactory(
            household=household, amount_due=Decimal("50"), due_date=date(2026, 3, 10)
        )
        BillFactory(household=household, amount_due=Decimal("70"), due_date=date(2026, 3, 18))
        BillFactory(household=household, amount_due=Decimal("500"), due_date=date(2026, 4, 30))
        PaymentFactory(bill=overdue, amount=Decimal("20"), paid_on=date(2026, 3, 11))
        overdue.amount_paid, overdue.status = Decimal("20"), "partial"
        overdue.save()
        expense(household, "15", TODAY)

        s = analytics.dashboard_summary(household, TODAY)
        assert s.bills_this_month == Decimal("120")
        assert s.paid_this_month == Decimal("20")
        assert s.overdue_total == Decimal("30") and s.overdue_count == 1
        assert s.due_soon_total == Decimal("70") and s.due_soon_count == 1
        assert s.outstanding == Decimal("600")
        assert s.remaining_budget == Decimal("3000") - Decimal("120") - Decimal("15")

    def test_chart_payload_uses_strings_not_floats(self, household):
        expense(household, "19.99", TODAY)
        payload = analytics.chart_payload(analytics.dashboard_summary(household, TODAY))
        assert payload["categories"]["values"] == ["19.99"]
        assert all(isinstance(v, str) for v in payload["trend"]["other"])
