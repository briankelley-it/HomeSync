"""Shared REST API building blocks.

Every household resource lives under ``/api/v1/households/<household_pk>/``.
``HouseholdRolePermission`` resolves the caller's membership for that
household (404 if none, so other households' IDs are not even confirmed to
exist), allows reads for any member, and requires ``write_role`` for writes.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import permissions, serializers, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.households.models import Membership, Role


class HouseholdRolePermission(permissions.BasePermission):
    message = "Your household role does not allow this action."

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        membership = (
            Membership.objects.filter(
                user=request.user, household_id=view.kwargs.get("household_pk")
            )
            .select_related("household")
            .first()
        )
        if membership is None:
            raise NotFound("Household not found.")
        view.membership = membership
        view.household = membership.household
        if request.method in permissions.SAFE_METHODS:
            return True
        return membership.has_role(getattr(view, "write_role", Role.MEMBER))


class HouseholdScopedViewSet(viewsets.ModelViewSet):
    """ModelViewSet restricted to one household, with role-based writes."""

    permission_classes = [permissions.IsAuthenticated, HouseholdRolePermission]
    write_role = Role.MEMBER
    household = None
    membership = None

    def get_queryset(self):
        return super().get_queryset().filter(household=self.household)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["household"] = self.household
        return context

    def perform_create(self, serializer):
        serializer.save(household=self.household)


class HouseholdScopedSerializer(serializers.ModelSerializer):
    """Restricts listed related fields to the household in the serializer context."""

    household_scoped_fields: tuple[str, ...] = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        household = self.context.get("household")
        for name in self.household_scoped_fields:
            field = self.fields.get(name)
            if field is not None and household is not None and not field.read_only:
                field.queryset = field.queryset.filter(household=household)


def raise_drf(exc: DjangoValidationError):
    """Translate a Django ValidationError from the service layer into a 400."""
    detail = exc.message_dict if hasattr(exc, "error_dict") else exc.messages
    raise DRFValidationError(detail) from exc
