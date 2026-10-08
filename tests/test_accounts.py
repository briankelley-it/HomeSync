import pytest
from django.core import mail
from django.test import override_settings
from django.urls import reverse

from apps.accounts.models import User

from .factories import UserFactory

pytestmark = pytest.mark.django_db


class TestUserModel:
    def test_create_user_normalizes_email(self):
        user = User.objects.create_user("Alice@Example.COM", "pw-1234567890")
        assert user.email == "alice@example.com"
        assert user.check_password("pw-1234567890")
        assert not user.is_staff

    def test_create_user_requires_email(self):
        with pytest.raises(ValueError):
            User.objects.create_user("", "pw")

    def test_create_superuser(self):
        admin = User.objects.create_superuser("root@example.com", "pw-1234567890")
        assert admin.is_staff and admin.is_superuser

    def test_initials_and_display_name(self):
        user = UserFactory(first_name="Ada", last_name="Lovelace", email="ada@example.com")
        assert user.initials == "AL"
        assert user.display_name == "Ada Lovelace"
        nameless = UserFactory(first_name="", last_name="", email="zed@example.com")
        assert nameless.display_name == "zed"


class TestRegistration:
    def test_register_logs_in_and_redirects_to_household_setup(self, client):
        response = client.post(
            reverse("accounts:register"),
            {
                "first_name": "Sam",
                "last_name": "Rivera",
                "email": "Sam@Example.com",
                "password1": "a-very-long-passphrase",
                "password2": "a-very-long-passphrase",
            },
        )
        assert response.status_code == 302
        assert response.url == reverse("households:create")
        user = User.objects.get(email="sam@example.com")
        assert int(client.session["_auth_user_id"]) == user.pk

    def test_duplicate_email_is_rejected_case_insensitively(self, client):
        UserFactory(email="taken@example.com")
        response = client.post(
            reverse("accounts:register"),
            {
                "first_name": "X",
                "email": "TAKEN@example.com",
                "password1": "a-very-long-passphrase",
                "password2": "a-very-long-passphrase",
            },
        )
        assert response.status_code == 200
        assert "already exists" in response.content.decode()

    def test_weak_password_rejected(self, client):
        response = client.post(
            reverse("accounts:register"),
            {"first_name": "X", "email": "x@example.com", "password1": "123", "password2": "123"},
        )
        assert response.status_code == 200
        assert not User.objects.filter(email="x@example.com").exists()


class TestLoginLogout:
    def test_login_with_email(self, client, password):
        user = UserFactory(email="login@example.com")
        response = client.post(
            reverse("accounts:login"), {"username": "LOGIN@example.com", "password": password}
        )
        assert response.status_code == 302
        assert int(client.session["_auth_user_id"]) == user.pk

    def test_login_wrong_password(self, client):
        UserFactory(email="login@example.com")
        response = client.post(
            reverse("accounts:login"), {"username": "login@example.com", "password": "nope"}
        )
        assert response.status_code == 200
        assert "_auth_user_id" not in client.session

    def test_logout_requires_post(self, auth_client):
        assert auth_client.get(reverse("accounts:logout")).status_code == 405
        response = auth_client.post(reverse("accounts:logout"))
        assert response.status_code == 302
        assert "_auth_user_id" not in auth_client.session

    @override_settings(RATELIMIT_ENABLE=True)
    def test_login_is_rate_limited(self, client):
        url = reverse("accounts:login")
        statuses = [
            client.post(url, {"username": "a@example.com", "password": "bad"}).status_code
            for _ in range(7)
        ]
        assert statuses[-1] == 429


class TestPasswordReset:
    def test_reset_email_sent_for_existing_user(self, client):
        UserFactory(email="reset@example.com")
        response = client.post(reverse("accounts:password_reset"), {"email": "reset@example.com"})
        assert response.status_code == 302
        assert len(mail.outbox) == 1
        assert "/accounts/password/reset/" in mail.outbox[0].body

    def test_no_email_for_unknown_address_but_same_response(self, client):
        response = client.post(reverse("accounts:password_reset"), {"email": "ghost@example.com"})
        assert response.status_code == 302
        assert len(mail.outbox) == 0


class TestProfile:
    def test_profile_requires_login(self, client):
        response = client.get(reverse("accounts:profile"))
        assert response.status_code == 302
        assert reverse("accounts:login") in response.url

    def test_update_profile(self, auth_client, user):
        response = auth_client.post(
            reverse("accounts:profile"), {"first_name": "New", "last_name": "Name"}
        )
        assert response.status_code == 302
        user.refresh_from_db()
        assert user.first_name == "New"
