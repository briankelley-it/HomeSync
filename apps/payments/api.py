from datetime import date

from rest_framework import mixins, serializers, viewsets

from apps.core.api import HouseholdRolePermission

from . import services
from .models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    recorded_by = serializers.EmailField(source="recorded_by.email", read_only=True, default=None)

    class Meta:
        model = Payment
        fields = [
            "id",
            "bill",
            "amount",
            "paid_on",
            "method",
            "reference",
            "notes",
            "recorded_by",
            "created_at",
        ]
        read_only_fields = ["bill", "recorded_by", "created_at"]


class PaymentViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Payment history. Record payments via ``POST bills/<id>/payments/``.

    Filters: ``?paid_after``, ``?paid_before`` (ISO dates), ``?bill``.
    """

    serializer_class = PaymentSerializer
    permission_classes = [HouseholdRolePermission]

    def get_queryset(self):
        qs = Payment.objects.filter(household=self.household).select_related("recorded_by")
        params = self.request.query_params
        for param, lookup in (("paid_after", "paid_on__gte"), ("paid_before", "paid_on__lte")):
            if value := params.get(param):
                try:
                    qs = qs.filter(**{lookup: date.fromisoformat(value)})
                except ValueError as exc:
                    raise serializers.ValidationError({param: "Use YYYY-MM-DD."}) from exc
        if params.get("bill", "").isdigit():
            qs = qs.filter(bill_id=params["bill"])
        return qs

    def perform_destroy(self, instance):
        services.delete_payment(payment=instance, actor=self.request.user)
