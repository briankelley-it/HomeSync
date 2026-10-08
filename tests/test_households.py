from datetime import timedelta

import pytest
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.households import services
from apps.households.middleware import SESSION_KEY
from apps.households.models import Invitation, Membership, Role

from .factories import HouseholdFactory, MembershipFactory, UserFactory

pytestmark = pytest.mark.django_db


class TestHouseholdServices:
    def test_create_household_makes_creator_owner(self):
        user = UserFactory()
        household = services.create_household(user=user, name="Maple St", currency="CAD")
        membership = Membership.objects.get(household=household, user=user)
        assert membership.role == Role.OWNER
        assert household.activity.count() == 1

    def test_role_ranks(self, make_member):
        viewer = make_member(Role.VIEWER)
        member = make_member(Role.MEMBER)
        admin = make_member(Role.ADMIN)
        assert not viewer.can_edit
        assert member.can_edit and not member.can_manage
        assert admin.can_manage and not admin.is_owner

    def test_cannot_remove_last_owner(self, owner):
        with pytest.raises(ValidationError):
            services.remove_member(actor=owner, target=owner)

    def test_cannot_demote_last_owner(self, owner):
        with pytest.raises(ValidationError):
            services.change_role(actor=owner, target=owner, role=Role.ADMIN)

    def test_admin_cannot_promote_to_owner(self, make_member):
        admin = make_member(Role.ADMIN)
        member = make_member(Role.MEMBER)
        with pytest.raises(PermissionDenied):
            services.change_role(actor=admin, target=member, role=Role.OWNER)

    def test_admin_cannot_remove_owner(self, owner, make_member):
        admin = make_member(Role.ADMIN)
        with pytest.raises(PermissionDenied):
            services.remove_member(actor=admin, target=owner)

    def test_member_cannot_invite(self, household, make_member):
        member = make_member(Role.MEMBER)
        with pytest.raises(PermissionDenied):
            services.invite_member(
                household=household, invited_by=member, email="a@b.com", role=Role.VIEWER
            )


class TestInvitations:
    def test_token_is_stored_hashed(self, household, owner):
        invitation, raw = services.invite_member(
            household=household, invited_by=owner, email="New@Example.com", role=Role.MEMBER
        )
        assert invitation.email == "new@example.com"
        assert raw not in invitation.token_hash
        assert Invitation.find_pending(raw) == invitation

    def test_duplicate_pending_invitation_rejected(self, household, owner):
        services.invite_member(
            household=household, invited_by=owner, email="a@b.com", role="member"
        )
        with pytest.raises(ValidationError):
            services.invite_member(
                household=household, invited_by=owner, email="A@B.com", role="member"
            )

    def test_accept_flow_via_views(self, client, household, owner):
        invitation, raw = services.invite_member(
            household=household, invited_by=owner, email="joiner@example.com", role=Role.VIEWER
        )
        joiner = UserFactory(email="joiner@example.com")
        client.force_login(joiner)
        url = reverse("households:accept_invitation", args=[raw])
        assert client.get(url).status_code == 200
        response = client.post(url)
        assert response.status_code == 302
        membership = Membership.objects.get(household=household, user=joiner)
        assert membership.role == Role.VIEWER
        assert client.session[SESSION_KEY] == household.pk
        invitation.refresh_from_db()
        assert invitation.accepted_at is not None
        # A used token is no longer valid.
        assert client.get(url).status_code == 404

    def test_wrong_email_cannot_accept(self, household, owner):
        invitation, _ = services.invite_member(
            household=household, invited_by=owner, email="right@example.com", role="member"
        )
        with pytest.raises(PermissionDenied):
            services.accept_invitation(invitation=invitation, user=UserFactory())

    def test_expired_invitation_is_invalid(self, client, household, owner):
        invitation, raw = services.invite_member(
            household=household, invited_by=owner, email="late@example.com", role="member"
        )
        Invitation.objects.filter(pk=invitation.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        client.force_login(UserFactory(email="late@example.com"))
        assert client.get(reverse("households:accept_invitation", args=[raw])).status_code == 404

    def test_invite_view_sends_email(
        self, auth_client, household, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            response = auth_client.post(
                reverse("households:members"), {"email": "friend@example.com", "role": "member"}
            )
        assert response.status_code == 302
        assert len(mail.outbox) == 1
        assert "/households/invitations/" in mail.outbox[0].body

    def test_anonymous_user_redirected_to_login(self, client, household, owner):
        _, raw = services.invite_member(
            household=household, invited_by=owner, email="anon@example.com", role="member"
        )
        response = client.get(reverse("households:accept_invitation", args=[raw]))
        assert response.status_code == 302
        assert reverse("accounts:login") in response.url


class TestMiddlewareAndViews:
    def test_user_without_household_is_sent_to_onboarding(self, client):
        client.force_login(UserFactory())
        response = client.get(reverse("core:dashboard"))
        assert response.status_code == 302
        assert response.url == reverse("households:create")

    def test_create_household_view(self, client):
        user = UserFactory()
        client.force_login(user)
        response = client.post(
            reverse("households:create"), {"name": "Lake House", "currency": "USD"}
        )
        assert response.status_code == 302
        assert user.memberships.get().household.name == "Lake House"

    def test_dashboard_renders(self, auth_client, household):
        response = auth_client.get(reverse("core:dashboard"))
        assert response.status_code == 200
        assert household.name in response.content.decode()

    def test_cannot_switch_to_foreign_household(self, auth_client, other_household):
        response = auth_client.post(reverse("households:switch"), {"household": other_household.pk})
        assert response.status_code == 404

    def test_switch_between_own_households(self, auth_client, user):
        second = MembershipFactory(user=user, household=HouseholdFactory(name="Cabin")).household
        auth_client.post(reverse("households:switch"), {"household": second.pk})
        response = auth_client.get(reverse("core:dashboard"))
        assert response.context["household"] == second

    def test_stale_session_household_falls_back(self, auth_client, household, other_household):
        session = auth_client.session
        session[SESSION_KEY] = other_household.pk  # not a member there
        session.save()
        response = auth_client.get(reverse("core:dashboard"))
        assert response.context["household"] == household

    def test_settings_require_admin(self, client_for, make_member):
        member = make_member(Role.MEMBER)
        client = client_for(member.user)
        assert client.get(reverse("households:settings")).status_code == 403

    def test_viewer_cannot_post_invitation(self, client_for, make_member):
        viewer = make_member(Role.VIEWER)
        client = client_for(viewer.user)
        response = client.post(
            reverse("households:members"), {"email": "x@example.com", "role": "viewer"}
        )
        assert response.status_code == 403

    def test_cannot_modify_member_of_other_household(self, auth_client, other_household):
        foreign = other_household.memberships.first()
        response = auth_client.post(
            reverse("households:change_role", args=[foreign.pk]), {"role": "viewer"}
        )
        assert response.status_code == 404

    def test_member_can_leave(self, client_for, make_member):
        member = make_member(Role.MEMBER)
        client = client_for(member.user)
        response = client.post(reverse("households:remove_member", args=[member.pk]))
        assert response.status_code == 302
        assert not Membership.objects.filter(pk=member.pk).exists()

    def test_health_endpoint(self, client):
        assert client.get(reverse("core:health")).json() == {"status": "ok"}
