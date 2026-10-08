import factory

from apps.accounts.models import User
from apps.households.models import Household, Membership, Role


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
