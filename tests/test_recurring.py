from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.bills import services
from apps.bills.models import Bill
from apps.bills.recurrence import occurrences

from .factories import PaymentFactory, RecurringBillFactory

TODAY = date(2026, 1, 10)


class TestOccurrences:
    """Pure date logic: no database needed."""

    def _dates(self, start, freq, ws, we, end=None):
        return list(occurrences(start, freq, window_start=ws, window_end=we, end_date=end))

    def test_monthly_end_of_month_does_not_drift(self):
        dates = self._dates(date(2026, 1, 31), "monthly", date(2026, 1, 1), date(2026, 5, 31))
        assert dates == [
            date(2026, 1, 31),
            date(2026, 2, 28),
            date(2026, 3, 31),
            date(2026, 4, 30),
            date(2026, 5, 31),
        ]

    def test_weekly(self):
        dates = self._dates(date(2026, 1, 5), "weekly", date(2026, 1, 10), date(2026, 1, 31))
        assert dates == [date(2026, 1, 12), date(2026, 1, 19), date(2026, 1, 26)]

    def test_quarterly_and_annual(self):
        q = self._dates(date(2026, 1, 15), "quarterly", date(2026, 1, 1), date(2026, 12, 31))
        assert q == [date(2026, 1, 15), date(2026, 4, 15), date(2026, 7, 15), date(2026, 10, 15)]
        a = self._dates(date(2024, 2, 29), "annual", date(2024, 1, 1), date(2028, 12, 31))
        assert a == [date(2024, 2, 29), date(2025, 2, 28), date(2026, 2, 28), date(2027, 2, 28),
                     date(2028, 2, 29)]  # fmt: skip

    def test_respects_end_date(self):
        dates = self._dates(
            date(2026, 1, 1), "monthly", date(2026, 1, 1), date(2026, 12, 31), end=date(2026, 3, 1)
        )
        assert dates == [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)]


@pytest.mark.django_db
class TestGeneration:
    def test_generates_within_horizon(self, household):
        schedule = RecurringBillFactory(household=household, start_date=date(2026, 1, 15))
        created = services.generate_bills(schedule, TODAY)
        due = list(schedule.bills.order_by("due_date").values_list("due_date", flat=True))
        assert created == 2
        assert due == [date(2026, 1, 15), date(2026, 2, 15)]  # horizon = 60 days
        bill = schedule.bills.first()
        assert bill.amount_due == schedule.amount and bill.household == household

    def test_running_twice_creates_no_duplicates(self, household):
        schedule = RecurringBillFactory(household=household, start_date=date(2026, 1, 15))
        services.generate_bills(schedule, TODAY)
        assert services.generate_bills(schedule, TODAY) == 0
        assert services.generate_bills(schedule, TODAY + timedelta(days=1)) == 0
        assert schedule.bills.count() == 2

    def test_advances_as_time_passes(self, household):
        schedule = RecurringBillFactory(household=household, start_date=date(2026, 1, 15))
        services.generate_bills(schedule, TODAY)
        # Horizon moves to Apr 21: Mar 15 and Apr 15 are new.
        assert services.generate_bills(schedule, date(2026, 2, 20)) == 2
        assert schedule.bills.filter(due_date=date(2026, 4, 15)).exists()

    def test_deleted_occurrence_is_not_recreated(self, household):
        schedule = RecurringBillFactory(household=household, start_date=date(2026, 1, 15))
        services.generate_bills(schedule, TODAY)
        schedule.bills.get(due_date=date(2026, 2, 15)).delete()  # user skipped February
        services.generate_bills(schedule, TODAY + timedelta(days=2))
        assert not schedule.bills.filter(due_date=date(2026, 2, 15)).exists()

    def test_lookback_limits_backfill(self, household):
        schedule = RecurringBillFactory(household=household, start_date=date(2025, 1, 1))
        services.generate_bills(schedule, TODAY)
        due = sorted(schedule.bills.values_list("due_date", flat=True))
        assert due[0] == date(2026, 1, 1)  # not a year of overdue bills

    def test_inactive_schedule_generates_nothing(self, household):
        schedule = RecurringBillFactory(household=household, is_active=False)
        assert services.generate_bills(schedule, TODAY) == 0

    def test_generate_all(self, household, other_household):
        RecurringBillFactory(household=household, start_date=TODAY)
        RecurringBillFactory(household=other_household, start_date=TODAY)
        # Jan 10, Feb 10, Mar 10 (horizon ends Mar 11) for each household.
        assert services.generate_all_recurring_bills(TODAY) == 6

    def test_editing_amount_updates_unpaid_future_bills_only(self, household, user):
        schedule = RecurringBillFactory(
            household=household, start_date=date(2026, 1, 15), amount=Decimal("50")
        )
        services.save_recurring_bill(schedule=schedule, actor=user, today=TODAY)
        jan = schedule.bills.get(due_date=date(2026, 1, 15))
        PaymentFactory(bill=jan, amount=Decimal("50"))
        jan.status = "paid"
        jan.save()

        schedule.amount = Decimal("65")
        services.save_recurring_bill(schedule=schedule, actor=user, today=TODAY)

        amounts = dict(schedule.bills.values_list("due_date", "amount_due"))
        assert amounts[date(2026, 1, 15)] == Decimal("50")  # paid history untouched
        assert amounts[date(2026, 2, 15)] == Decimal("65")
        assert Bill.objects.filter(recurring=schedule).count() == 2

    def test_monthly_recurring_total(self, household):
        RecurringBillFactory(household=household, amount=Decimal("120"), frequency="annual")
        RecurringBillFactory(household=household, amount=Decimal("30"), frequency="quarterly")
        RecurringBillFactory(household=household, amount=Decimal("100"), frequency="monthly")
        assert services.monthly_recurring_total(household) == Decimal("120.00")
