from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.core import mail
from django.urls import reverse

from apps.bills.tasks import generate_recurring_bills
from apps.households.models import Role
from apps.notifications import services
from apps.notifications.models import NotificationPreference, ReminderLog
from apps.notifications.tasks import send_bill_reminders

from .factories import BillFactory, PropertyFactory, RecurringBillFactory

pytestmark = pytest.mark.django_db
TODAY = date(2026, 5, 10)


def bill_due(household, days, **kwargs):
    return BillFactory(household=household, due_date=TODAY + timedelta(days=days), **kwargs)


class TestReminderSelection:
    def test_due_soon_respects_days_before(self, household, owner):
        bill_due(household, 3, name="Soon")
        bill_due(household, 4, name="Later")
        sent = services.send_bill_reminders(TODAY)
        assert sent == 1
        body = mail.outbox[0].body
        assert "Soon" in body and "Later" not in body
        assert mail.outbox[0].to == [owner.user.email]

    def test_custom_lead_time(self, household, owner):
        NotificationPreference.objects.create(user=owner.user, remind_days_before=10)
        bill_due(household, 9, name="Insurance")
        services.send_bill_reminders(TODAY)
        assert "Insurance" in mail.outbox[0].body

    def test_overdue_alert(self, household, owner):
        bill_due(household, -2, name="Late water", amount_due=Decimal("40.00"))
        services.send_bill_reminders(TODAY)
        body = mail.outbox[0].body
        assert "OVERDUE" in body and "Late water" in body and "$40.00" in body

    def test_preferences_can_disable(self, household, owner):
        NotificationPreference.objects.create(
            user=owner.user, email_reminders=False, overdue_alerts=False
        )
        bill_due(household, 1)
        bill_due(household, -1)
        assert services.send_bill_reminders(TODAY) == 0

    def test_paid_bills_are_skipped(self, household, owner):
        bill_due(household, 1, status="paid")
        assert services.send_bill_reminders(TODAY) == 0

    def test_long_overdue_bills_are_not_nagged(self, household, owner):
        bill_due(household, -40)
        assert services.send_bill_reminders(TODAY) == 0

    def test_each_reminder_is_sent_once(self, household, owner):
        bill = bill_due(household, 2)
        services.send_bill_reminders(TODAY)
        services.send_bill_reminders(TODAY + timedelta(days=1))
        assert len(mail.outbox) == 1
        assert ReminderLog.objects.get(bill=bill).kind == "due_soon"
        # It can still get a separate overdue alert later.
        services.send_bill_reminders(TODAY + timedelta(days=3))
        assert len(mail.outbox) == 2

    def test_property_members_only(self, household, owner, make_member):
        tenant = make_member(Role.MEMBER)
        cabin = PropertyFactory(household=household)
        cabin.members.add(tenant)
        bill_due(household, 1, property=cabin)
        services.send_bill_reminders(TODAY)
        assert [m.to for m in mail.outbox] == [[tenant.user.email]]

    def test_one_digest_per_household(self, household, owner):
        bill_due(household, 1)
        bill_due(household, 2)
        bill_due(household, -1)
        assert services.send_bill_reminders(TODAY) == 1
        message = mail.outbox[0]
        assert "3 bill reminders" in message.subject
        assert message.alternatives[0][1] == "text/html"

    def test_other_households_never_leak(self, household, owner, other_household):
        bill_due(other_household, 1, name="Secret bill")
        services.send_bill_reminders(TODAY)
        for message in mail.outbox:
            if owner.user.email in message.to:
                assert "Secret bill" not in message.body

    def test_failed_send_is_retried_next_run(self, household, owner):
        bill_due(household, 1)
        with (
            mock.patch.object(services, "send_reminder_email", side_effect=ConnectionError),
            pytest.raises(ConnectionError),
        ):
            services.send_bill_reminders(TODAY)
        assert not ReminderLog.objects.exists()  # rolled back
        assert services.send_bill_reminders(TODAY) == 1


class TestTasks:
    def test_reminder_task(self, household, owner):
        bill_due(household, 0)
        assert send_bill_reminders.delay(TODAY.isoformat()).get() == 1

    def test_generate_recurring_task(self, household):
        RecurringBillFactory(household=household, start_date=TODAY)
        # May 10 and Jun 10; Jul 10 is past the 60-day horizon (Jul 9).
        assert generate_recurring_bills.delay(TODAY.isoformat()).get() == 2
        assert generate_recurring_bills.delay(TODAY.isoformat()).get() == 0

    def test_beat_schedule_registered(self, settings):
        tasks = {entry["task"] for entry in settings.CELERY_BEAT_SCHEDULE.values()}
        assert tasks == {
            "apps.bills.tasks.generate_recurring_bills",
            "apps.notifications.tasks.send_bill_reminders",
        }


class TestPreferencesView:
    def test_update_preferences(self, auth_client, user):
        response = auth_client.post(
            reverse("notifications:preferences"),
            {"email_reminders": "on", "remind_days_before": "7"},
        )
        assert response.status_code == 302
        pref = NotificationPreference.objects.get(user=user)
        assert pref.remind_days_before == 7 and not pref.overdue_alerts

    def test_rejects_out_of_range(self, auth_client, user):
        response = auth_client.post(
            reverse("notifications:preferences"), {"remind_days_before": "90"}
        )
        assert response.status_code == 200
        assert not NotificationPreference.objects.filter(remind_days_before=90).exists()
