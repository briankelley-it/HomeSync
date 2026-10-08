"""Household financial analytics.

Spending is what a household actually recorded: bill payments (dated by
``paid_on``) plus one-off expenses (dated by ``spent_on``). All arithmetic is
done with ``Decimal`` in the database; values are converted to strings only at
the JSON boundary for Chart.js.
"""

import calendar
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth

from apps.bills.models import Bill
from apps.payments.models import Payment

from .models import Budget, Expense, IncomeSource

ZERO = Decimal("0.00")


def month_bounds(day: date) -> tuple[date, date]:
    first = day.replace(day=1)
    last = day.replace(day=calendar.monthrange(day.year, day.month)[1])
    return first, last


def _scoped(queryset, prop, field="property"):
    return queryset.filter(**{field: prop}) if prop else queryset


def monthly_income(household) -> Decimal:
    sources = IncomeSource.objects.filter(household=household, is_active=True)
    return sum((s.monthly_amount for s in sources), ZERO)


def spending_between(household, start: date, end: date, prop=None) -> Decimal:
    payments = _scoped(
        Payment.objects.filter(household=household, paid_on__range=(start, end)),
        prop,
        "bill__property",
    ).aggregate(total=Sum("amount"))["total"]
    expenses = _scoped(
        Expense.objects.filter(household=household, spent_on__range=(start, end)), prop
    ).aggregate(total=Sum("amount"))["total"]
    return (payments or ZERO) + (expenses or ZERO)


def spending_trend(household, today: date, months: int = 6, prop=None) -> list[dict]:
    """Monthly totals for the last ``months`` months (oldest first)."""
    first_month = today.replace(day=1) - relativedelta(months=months - 1)
    totals: dict[date, dict[str, Decimal]] = defaultdict(lambda: {"bills": ZERO, "other": ZERO})

    payments = _scoped(
        Payment.objects.filter(household=household, paid_on__gte=first_month),
        prop,
        "bill__property",
    )
    for row in (
        payments.annotate(month=TruncMonth("paid_on")).values("month").annotate(t=Sum("amount"))
    ):
        totals[row["month"]]["bills"] += row["t"]

    expenses = _scoped(Expense.objects.filter(household=household, spent_on__gte=first_month), prop)
    for row in (
        expenses.annotate(month=TruncMonth("spent_on")).values("month").annotate(t=Sum("amount"))
    ):
        totals[row["month"]]["other"] += row["t"]

    result = []
    for i in range(months):
        month = first_month + relativedelta(months=i)
        bucket = totals[month]
        result.append(
            {
                "month": month,
                "label": month.strftime("%b %Y"),
                "bills": bucket["bills"],
                "other": bucket["other"],
                "total": bucket["bills"] + bucket["other"],
            }
        )
    return result


def category_breakdown(household, start: date, end: date, prop=None) -> list[dict]:
    """Spending per category between two dates, largest first."""
    totals: dict[int, dict] = {}

    def add(rows, prefix):
        for row in rows:
            entry = totals.setdefault(
                row[f"{prefix}id"],
                {"name": row[f"{prefix}name"], "color": row[f"{prefix}color"], "total": ZERO},
            )
            entry["total"] += row["t"]

    payments = _scoped(
        Payment.objects.filter(household=household, paid_on__range=(start, end)),
        prop,
        "bill__property",
    )
    add(
        payments.values("bill__category__id", "bill__category__name", "bill__category__color")
        .annotate(t=Sum("amount"))
        .order_by(),
        "bill__category__",
    )
    expenses = _scoped(
        Expense.objects.filter(household=household, spent_on__range=(start, end)), prop
    )
    add(
        expenses.values("category__id", "category__name", "category__color")
        .annotate(t=Sum("amount"))
        .order_by(),
        "category__",
    )
    return sorted(totals.values(), key=lambda e: e["total"], reverse=True)


def budget_progress(household, today: date) -> list[dict]:
    """Each budget with this month's spending in its category (and property)."""
    start, end = month_bounds(today)
    rows = []
    for budget in Budget.objects.filter(household=household).select_related("category", "property"):
        payments = Payment.objects.filter(
            household=household, paid_on__range=(start, end), bill__category=budget.category
        )
        expenses = Expense.objects.filter(
            household=household, spent_on__range=(start, end), category=budget.category
        )
        if budget.property_id:
            payments = payments.filter(bill__property=budget.property)
            expenses = expenses.filter(property=budget.property)
        spent = (payments.aggregate(t=Sum("amount"))["t"] or ZERO) + (
            expenses.aggregate(t=Sum("amount"))["t"] or ZERO
        )
        rows.append(
            {
                "budget": budget,
                "spent": spent,
                "remaining": budget.amount - spent,
                "percent": int(min(spent / budget.amount * 100, 999)),
                "over": spent > budget.amount,
            }
        )
    return rows


@dataclass
class DashboardSummary:
    month_start: date
    month_end: date
    bills_this_month: Decimal
    bills_this_month_count: int
    paid_this_month: Decimal
    due_soon_total: Decimal
    due_soon_count: int
    overdue_total: Decimal
    overdue_count: int
    outstanding: Decimal
    income: Decimal
    expenses_this_month: Decimal
    remaining_budget: Decimal
    trend: list[dict] = field(default_factory=list)
    categories: list[dict] = field(default_factory=list)


def _open_balance(queryset) -> tuple[Decimal, int]:
    row = queryset.aggregate(due=Sum("amount_due"), paid=Sum("amount_paid"), n=Count("id"))
    return (row["due"] or ZERO) - (row["paid"] or ZERO), row["n"]


def dashboard_summary(household, today: date, prop=None) -> DashboardSummary:
    start, end = month_bounds(today)
    bills = _scoped(Bill.objects.filter(household=household), prop)

    month_bills = bills.filter(due_date__range=(start, end)).aggregate(
        total=Sum("amount_due"), n=Count("id")
    )
    paid_this_month = (
        _scoped(
            Payment.objects.filter(household=household, paid_on__range=(start, end)),
            prop,
            "bill__property",
        ).aggregate(t=Sum("amount"))["t"]
        or ZERO
    )
    expenses_this_month = (
        _scoped(
            Expense.objects.filter(household=household, spent_on__range=(start, end)), prop
        ).aggregate(t=Sum("amount"))["t"]
        or ZERO
    )

    due_soon_total, due_soon_count = _open_balance(bills.due_soon(today))
    overdue_total, overdue_count = _open_balance(bills.overdue(today))
    outstanding, _ = _open_balance(bills.open())
    income = monthly_income(household)
    bills_this_month = month_bills["total"] or ZERO

    return DashboardSummary(
        month_start=start,
        month_end=end,
        bills_this_month=bills_this_month,
        bills_this_month_count=month_bills["n"],
        paid_this_month=paid_this_month,
        due_soon_total=due_soon_total,
        due_soon_count=due_soon_count,
        overdue_total=overdue_total,
        overdue_count=overdue_count,
        outstanding=outstanding,
        income=income,
        expenses_this_month=expenses_this_month,
        # Estimated: what is left after this month's bills and one-off spending.
        remaining_budget=income - bills_this_month - expenses_this_month,
        trend=spending_trend(household, today, prop=prop),
        categories=category_breakdown(household, start, end, prop=prop),
    )


def chart_payload(summary: DashboardSummary) -> dict:
    """JSON-safe data for Chart.js (Decimals become strings, never floats)."""
    return {
        "trend": {
            "labels": [m["label"] for m in summary.trend],
            "bills": [str(m["bills"]) for m in summary.trend],
            "other": [str(m["other"]) for m in summary.trend],
        },
        "categories": {
            "labels": [c["name"] for c in summary.categories],
            "values": [str(c["total"]) for c in summary.categories],
            "colors": [c["color"] for c in summary.categories],
        },
    }
