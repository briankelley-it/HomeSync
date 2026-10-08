import pytest

from apps.households.models import Role

from .factories import HouseholdFactory, MembershipFactory, UserFactory

PASSWORD = "correct-horse-battery"


@pytest.fixture
def password():
    return PASSWORD


@pytest.fixture
def household(db):
    return HouseholdFactory()


@pytest.fixture
def make_member(household):
    """Create a user with the given role in ``household``."""

    def _make(role=Role.MEMBER, **kwargs):
        return MembershipFactory(household=household, role=role, **kwargs)

    return _make


@pytest.fixture
def owner(make_member):
    return make_member(Role.OWNER)


@pytest.fixture
def user(owner):
    return owner.user


@pytest.fixture
def auth_client(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def client_for(client):
    """Return a test client logged in as the given user."""

    def _login(user):
        client.force_login(user)
        return client

    return _login


@pytest.fixture
def other_household(db):
    """A separate household (with its own owner) the main user must not see."""
    return MembershipFactory(household=HouseholdFactory(name="Other"), user=UserFactory()).household


@pytest.fixture(autouse=True)
def _clear_cache():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


__all__ = ["UserFactory", "HouseholdFactory", "MembershipFactory"]
