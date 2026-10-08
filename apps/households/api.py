from rest_framework import mixins, permissions, serializers, viewsets

from .models import Household


class HouseholdSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = Household
        fields = ["id", "name", "currency", "role", "created_at"]

    def get_role(self, household) -> str | None:
        user = self.context["request"].user
        membership = next((m for m in household.memberships.all() if m.user_id == user.pk), None)
        return membership.role if membership else None


class HouseholdViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Households the current user belongs to (read-only)."""

    serializer_class = HouseholdSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Household.objects.filter(memberships__user=self.request.user).prefetch_related(
            "memberships"
        )
