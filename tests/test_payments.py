import threading
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import connection
from django.utils import timezone

from apps.bills import services as bill_services
from apps.bills.models import Bill, BillStatus
from apps.payments import services
from apps.payments.forms import PaymentForm
from apps.payments.models import Payment

from .factories import BillFactory, PaymentFactory

TODAY = timezone.localdate()

pytestmark = pytest.mark.django_db


@pytest.fixture
def bill(household):
    return BillFactory(household=household, amount_due=Decimal("120.00"))


class TestRecordPayment:
    def test_full_payment_marks_bill_paid(self, bill, user):
        services.record_payment(
            bill=bill, amount=Decimal("120.00"), paid_on=TODAY, recorded_by=user
        )
        bill.refresh_from_db()
        assert bill.status == BillStatus.PAID
        assert bill.amount_paid == Decimal("120.00")
        assert bill.balance == Decimal("0.00")
        assert bill.paid_on == TODAY

    def test_partial_payments_accumulate(self, bill, user):
        services.record_payment(bill=bill, amount=Decimal("20.00"), paid_on=TODAY, recorded_by=user)
        bill.refresh_from_db()
        assert bill.status == BillStatus.PARTIAL
        assert bill.balance == Decimal("100.00")
        assert bill.paid_on is None

        services.record_payment(
            bill=bill, amount=Decimal("100.00"), paid_on=TODAY, recorded_by=user
        )
        bill.refresh_from_db()
        assert bill.status == BillStatus.PAID
        assert bill.payments.count() == 2

    def test_overpayment_rejected(self, bill, user):
        with pytest.raises(ValidationError):
            services.record_payment(
                bill=bill, amount=Decimal("120.01"), paid_on=TODAY, recorded_by=user
            )
        assert not Payment.objects.exists()

    def test_zero_or_negative_rejected(self, bill, user):
        for amount in (Decimal("0"), Decimal("-5")):
            with pytest.raises(ValidationError):
                services.record_payment(bill=bill, amount=amount, paid_on=TODAY, recorded_by=user)

    def test_future_date_rejected(self, bill, user):
        with pytest.raises(ValidationError):
            services.record_payment(
                bill=bill,
                amount=Decimal("10"),
                paid_on=TODAY + timedelta(days=1),
                recorded_by=user,
            )

    def test_payment_logs_activity(self, bill, user):
        services.record_payment(bill=bill, amount=Decimal("10"), paid_on=TODAY, recorded_by=user)
        assert "partial payment" in bill.household.activity.first().description

    def test_bill_is_not_paid_without_a_payment(self, bill):
        """Nothing but a recorded payment may mark a bill paid."""
        bill.refresh_from_db()
        assert bill.status == BillStatus.UNPAID
        assert bill.amount_paid == Decimal("0.00")


class TestDeleteAndEdit:
    def test_deleting_payment_reopens_bill(self, bill, user):
        payment = services.record_payment(
            bill=bill, amount=Decimal("120"), paid_on=TODAY, recorded_by=user
        )
        services.delete_payment(payment=payment, actor=user)
        bill.refresh_from_db()
        assert bill.status == BillStatus.UNPAID
        assert bill.amount_paid == Decimal("0.00")

    def test_bill_with_payments_cannot_be_deleted(self, bill, user):
        PaymentFactory(bill=bill)
        with pytest.raises(ValidationError):
            bill_services.delete_bill(bill=bill, actor=user)
        assert Bill.objects.filter(pk=bill.pk).exists()

    def test_raising_amount_due_reopens_paid_bill(self, bill, user):
        services.record_payment(bill=bill, amount=Decimal("120"), paid_on=TODAY, recorded_by=user)
        bill.refresh_from_db()
        bill.amount_due = Decimal("150.00")
        bill_services.save_bill(bill=bill, actor=user)
        assert bill.status == BillStatus.PARTIAL
        assert bill.balance == Decimal("30.00")

    def test_outstanding_total(self, household, user):
        a = BillFactory(household=household, amount_due=Decimal("100"))
        BillFactory(household=household, amount_due=Decimal("50.25"))
        services.record_payment(bill=a, amount=Decimal("40"), paid_on=TODAY, recorded_by=user)
        assert services.outstanding_total(household) == Decimal("110.25")


class TestPaymentForm:
    def test_defaults_to_remaining_balance(self, bill):
        form = PaymentForm(bill=bill)
        assert form.initial["amount"] == Decimal("120.00")

    def test_rejects_more_than_balance(self, bill):
        form = PaymentForm(
            data={"amount": "500", "paid_on": TODAY.isoformat(), "method": "card"}, bill=bill
        )
        assert not form.is_valid()
        assert "amount" in form.errors


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(connection.vendor != "postgresql", reason="needs row-level locking")
def test_concurrent_payments_cannot_overpay(household, user):
    """Two simultaneous full payments: exactly one succeeds thanks to SELECT FOR UPDATE."""
    from django.db import connections

    bill = BillFactory(household=household, amount_due=Decimal("80.00"))
    barrier = threading.Barrier(2)
    results: list[str] = []

    def pay():
        try:
            barrier.wait()
            services.record_payment(
                bill=bill, amount=Decimal("80.00"), paid_on=TODAY, recorded_by=user
            )
            results.append("ok")
        except ValidationError:
            results.append("rejected")
        finally:
            connections.close_all()

    threads = [threading.Thread(target=pay) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results) == ["ok", "rejected"]
    bill.refresh_from_db()
    assert bill.amount_paid == Decimal("80.00")
    assert bill.payments.count() == 1
