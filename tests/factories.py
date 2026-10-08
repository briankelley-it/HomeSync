from datetime import timedelta
from decimal import Decimal

import factory
from django.utils import timezone

from apps.accounts.models import User
from apps.bills.models import Bill, Category, Frequency, RecurringBill
from apps.households.models import Household, Membership, Role
from apps.properties.models import Property


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    password = "correct-horse-battery"

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        return model_class.objects.create_user(*args, **kwargs)


class HouseholdFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Household

    name = factory.Sequence(lambda n: f"Household {n}")
    currency = "USD"


class MembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Membership

    household = factory.SubFactory(HouseholdFactory)
    user = factory.SubFactory(UserFactory)
    role = Role.OWNER


class PropertyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Property

    household = factory.SubFactory(HouseholdFactory)
    name = factory.Sequence(lambda n: f"Property {n}")


class CategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Category

    household = factory.SubFactory(HouseholdFactory)
    name = factory.Sequence(lambda n: f"Category {n}")


class BillFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Bill

    household = factory.SubFactory(HouseholdFactory)
    category = factory.LazyFunction(lambda: Category.objects.get(name="Electricity"))
    name = factory.Sequence(lambda n: f"Bill {n}")
    amount_due = Decimal("100.00")
    due_date = factory.LazyFunction(lambda: timezone.localdate() + timedelta(days=10))


class RecurringBillFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = RecurringBill

    household = factory.SubFactory(HouseholdFactory)
    category = factory.LazyFunction(lambda: Category.objects.get(name="Internet"))
    name = factory.Sequence(lambda n: f"Recurring {n}")
    amount = Decimal("59.99")
    frequency = Frequency.MONTHLY
    start_date = factory.LazyFunction(timezone.localdate)
