"""Create a demo household for local development and screenshots.

Refuses to run unless DEBUG=True so demo data can never reach production.
The demo password is read from the DEMO_USER_PASSWORD environment variable.
"""

import os
from datetime import timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.bills import services as bill_services
from apps.bills.models import Bill, Category, Frequency, RecurringBill
from apps.budgets.models import Budget, Expense, IncomeSource
from apps.households.models import Household, Membership, Role
from apps.households.services import create_household
from apps.payments.models import PaymentMethod
from apps.payments.services import record_payment
from apps.properties.models import Property

DEMO_EMAIL = "demo@houseledger.test"


class Command(BaseCommand):
    help = "Create a demo household with sample bills (development only)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing demo data first.")

    def handle(self, *args, reset=False, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo only runs with DJANGO_DEBUG=True.")
        password = os.environ.get("DEMO_USER_PASSWORD")
        if not password:
            raise CommandError("Set DEMO_USER_PASSWORD in your .env first.")

        if reset:
            Household.objects.filter(memberships__user__email=DEMO_EMAIL).delete()
            User.objects.filter(email__endswith="@houseledger.test").delete()
        if User.objects.filter(email=DEMO_EMAIL).exists():
            raise CommandError("Demo data already exists. Use --reset to recreate it.")

        with transaction.atomic():
            self._seed(password)
        self.stdout.write(self.style.SUCCESS(f"Demo household created. Sign in as {DEMO_EMAIL}."))

    def _seed(self, password: str) -> None:
        today = timezone.localdate()
        cat = {c.name: c for c in Category.objects.filter(household=None)}

        owner = User.objects.create_user(DEMO_EMAIL, password, first_name="Jordan", last_name="Lee")
        partner = User.objects.create_user(
            "sam@houseledger.test", password, first_name="Sam", last_name="Lee"
        )
        household = create_household(user=owner, name="Lee Family", currency="USD")
        partner_membership = Membership.objects.create(
            household=household, user=partner, role=Role.ADMIN
        )
        owner_membership = owner.memberships.get(household=household)

        home = Property.objects.create(
            household=household,
            name="Maple Street",
            property_type=Property.Type.HOUSE,
            address_line1="42 Maple Street",
            city="Portland",
            state="OR",
            is_primary=True,
        )
        home.members.set([owner_membership, partner_membership])
        cabin = Property.objects.create(
            household=household,
            name="Lakeside Cabin",
            property_type=Property.Type.VACATION,
            city="Bend",
            state="OR",
        )
        cabin.members.set([owner_membership])

        schedules = [
            ("Mortgage", "Evergreen Bank", "1850.00", Frequency.MONTHLY, 1, home, "Mortgage"),
            ("Electricity", "Portland Power", "142.30", Frequency.MONTHLY, 18, home, "Electricity"),
            ("Internet", "FiberNet", "79.99", Frequency.MONTHLY, 12, home, "Internet"),
            ("Water & sewer", "City Water", "96.40", Frequency.MONTHLY, 25, home, "Water"),
            ("Phone plan", "Cellular Co", "85.00", Frequency.MONTHLY, 8, None, "Phone"),
            ("Streaming", "StreamBox", "22.99", Frequency.MONTHLY, 3, None, "Subscriptions"),
            ("Cabin propane", "Highland Gas", "210.00", Frequency.QUARTERLY, 15, cabin, "Gas"),
            ("Home insurance", "Safe Harbor", "1320.00", Frequency.ANNUAL, 20, home, "Insurance"),
        ]
        start_month = today.replace(day=1) - relativedelta(months=5)
        for name, payee, amount, freq, day, prop, category in schedules:
            schedule = RecurringBill(
                household=household,
                property=prop,
                category=cat[category],
                name=name,
                payee=payee,
                amount=Decimal(amount),
                frequency=freq,
                start_date=start_month.replace(day=day),
                autopay=name in ("Mortgage", "Streaming"),
            )
            schedule.save()
            # Backfill five months of history (paid) so charts have data.
            for months_back in range(5, 0, -1):
                due = today.replace(day=1) - relativedelta(months=months_back)
                due = due.replace(day=day)
                if due < schedule.start_date:
                    continue
                if freq == Frequency.QUARTERLY and (5 - months_back) % 3:
                    continue
                if freq == Frequency.ANNUAL and months_back != 5:
                    continue
                variance = Decimal(1) + Decimal((months_back * 7) % 11 - 5) / 100
                if category not in ("Electricity", "Water", "Gas"):
                    variance = Decimal(1)  # fixed-price bills do not vary
                bill_amount = (Decimal(amount) * variance).quantize(Decimal("0.01"))
                bill = Bill.objects.create(
                    household=household,
                    property=prop,
                    category=cat[category],
                    recurring=schedule,
                    name=name,
                    payee=payee,
                    amount_due=bill_amount,
                    due_date=due,
                    created_by=owner,
                )
                record_payment(
                    bill=bill,
                    amount=bill_amount,
                    paid_on=min(due, today),
                    method=PaymentMethod.AUTOPAY if schedule.autopay else PaymentMethod.CARD,
                    recorded_by=owner,
                )
            schedule.generated_through = today - timedelta(days=32)
            schedule.save(update_fields=["generated_through"])
            bill_services.generate_bills(schedule, today)

        # Make one current bill overdue and one partially paid for a realistic picture.
        current = Bill.objects.filter(household=household, status="unpaid").order_by("due_date")
        overdue = current.filter(due_date__lt=today).first()
        if overdue is None:
            Bill.objects.create(
                household=household,
                property=home,
                category=cat["Maintenance"],
                name="Gutter cleaning",
                payee="Clearflow Services",
                amount_due=Decimal("180.00"),
                due_date=today - timedelta(days=4),
                created_by=partner,
            )
        upcoming = current.filter(due_date__gte=today, category=cat["Electricity"]).first()
        if upcoming:
            record_payment(
                bill=upcoming, amount=Decimal("50.00"), paid_on=today, recorded_by=partner
            )

        IncomeSource.objects.create(
            household=household,
            name="Jordan salary",
            amount=Decimal("3250.00"),
            frequency=IncomeSource.Frequency.BIWEEKLY,
            earner=owner_membership,
        )
        IncomeSource.objects.create(
            household=household,
            name="Sam consulting",
            amount=Decimal("2400.00"),
            frequency=IncomeSource.Frequency.MONTHLY,
            earner=partner_membership,
        )

        for name, limit in (("Groceries", "900"), ("Electricity", "160"), ("Subscriptions", "40")):
            Budget.objects.create(household=household, category=cat[name], amount=Decimal(limit))

        grocery_runs = [("Farmers market", "64.20"), ("Weekly groceries", "182.45")]
        for months_back in range(0, 6):
            month = today.replace(day=1) - relativedelta(months=months_back)
            for week in range(4):
                spent_on = month + timedelta(days=week * 7 + 2)
                if spent_on > today:
                    continue
                desc, amount = grocery_runs[week % 2]
                Expense.objects.create(
                    household=household,
                    category=cat["Groceries"],
                    description=desc,
                    amount=Decimal(amount) + Decimal(week * 3 + months_back),
                    spent_on=spent_on,
                    recorded_by=owner if week % 2 else partner,
                )
        Expense.objects.create(
            household=household,
            property=cabin,
            category=cat["Maintenance"],
            description="Dock repair supplies",
            amount=Decimal("236.80"),
            spent_on=today - timedelta(days=9),
            recorded_by=owner,
        )
