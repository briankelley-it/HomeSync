"""Business logic for households, memberships, and invitations."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import ROLE_RANK, ActivityLog, Household, Invitation, Membership, Role


def log_activity(household: Household, actor, verb: str, description: str) -> ActivityLog:
    return ActivityLog.objects.create(
        household=household, actor=actor, verb=verb, description=description[:255]
    )


@transaction.atomic
def create_household(*, user, name: str, currency: str = "USD") -> Household:
    """Create a household and make ``user`` its owner."""
    household = Household.objects.create(name=name, currency=currency, created_by=user)
    Membership.objects.create(household=household, user=user, role=Role.OWNER)
    log_activity(household, user, "created", f"{user.display_name} created the household")
    return household


def invite_member(*, household: Household, invited_by: Membership, email: str, role: str):
    """Create an invitation. Returns ``(invitation, raw_token)``."""
    if not invited_by.can_manage:
        raise PermissionDenied("Only admins can invite members.")
    if ROLE_RANK[Role(role)] > invited_by.rank:
        raise PermissionDenied("You cannot invite someone with a higher role than your own.")
    email = email.strip().lower()
    if household.memberships.filter(user__email__iexact=email).exists():
        raise ValidationError("That person is already a member of this household.")
    if household.invitations.pending().filter(email__iexact=email).exists():
        raise ValidationError("An invitation is already pending for that email address.")
    invitation, raw_token = Invitation.create_with_token(
        household=household, email=email, role=role, invited_by=invited_by.user
    )
    log_activity(household, invited_by.user, "invited", f"Invited {email} as {role}")
    return invitation, raw_token


@transaction.atomic
def accept_invitation(*, invitation: Invitation, user) -> Membership:
    invitation = Invitation.objects.select_for_update().get(pk=invitation.pk)
    if not invitation.is_pending:
        raise ValidationError("This invitation is no longer valid.")
    if invitation.email.lower() != user.email.lower():
        raise PermissionDenied("This invitation was sent to a different email address.")
    membership, _ = Membership.objects.get_or_create(
        household=invitation.household, user=user, defaults={"role": invitation.role}
    )
    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=["accepted_at", "updated_at"])
    log_activity(invitation.household, user, "joined", f"{user.display_name} joined the household")
    return membership


def _ensure_can_modify(actor: Membership, target: Membership) -> None:
    if actor.household_id != target.household_id:
        raise PermissionDenied
    if not actor.can_manage:
        raise PermissionDenied("Only admins can manage members.")
    if target.rank > actor.rank:
        raise PermissionDenied("You cannot modify a member with a higher role than your own.")


def _owner_count(household: Household) -> int:
    return household.memberships.filter(role=Role.OWNER).count()


@transaction.atomic
def change_role(*, actor: Membership, target: Membership, role: str) -> Membership:
    _ensure_can_modify(actor, target)
    if ROLE_RANK[Role(role)] > actor.rank:
        raise PermissionDenied("You cannot grant a role higher than your own.")
    if target.role == Role.OWNER and role != Role.OWNER and _owner_count(target.household) <= 1:
        raise ValidationError("A household must keep at least one owner.")
    target.role = role
    target.save(update_fields=["role", "updated_at"])
    log_activity(
        target.household,
        actor.user,
        "role",
        f"Changed the role of {target.user.display_name} to {role}",
    )
    return target


@transaction.atomic
def remove_member(*, actor: Membership, target: Membership) -> None:
    if actor.pk != target.pk:  # Leaving a household yourself needs no admin rights.
        _ensure_can_modify(actor, target)
    if target.role == Role.OWNER and _owner_count(target.household) <= 1:
        raise ValidationError("A household must keep at least one owner.")
    log_activity(
        target.household, actor.user, "removed", f"{target.user.display_name} left the household"
    )
    target.delete()
