from datetime import date

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.api import HouseholdScopedSerializer, HouseholdScopedViewSet, raise_drf
from apps.households.models import Role
from apps.payments import services as payment_services
from apps.payments.api import PaymentSerializer

from . import services
from .models import Bill, Category, RecurringBill


class CategorySerializer(serializers.ModelSerializer):
    is_builtin = serializers.BooleanField(read_only=True)

    class Meta:
        model = Category
        fields = ["id", "name", "color", "is_builtin"]

    def validate_name(self, value):
        household = self.context["household"]
        clash = Category.objects.for_household(household).filter(name__iexact=value.strip())
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("A category with this name already exists.")
        return value.strip()


class CategoryViewSet(HouseholdScopedViewSet):
    """Built-in categories are readable by everyone but only custom ones are writable."""

    serializer_class = CategorySerializer
    queryset = Category.objects.all()
    write_role = Role.ADMIN

    def get_queryset(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return Category.objects.for_household(self.household)
        return Category.objects.filter(household=self.household)


class CategoryRelatedField(serializers.PrimaryKeyRelatedField):
    def get_queryset(self):
        return Category.objects.for_household(self.context["household"])


class BillSerializer(HouseholdScopedSerializer):
    household_scoped_fields = ("property",)
    category = CategoryRelatedField()
    balance = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    display_status = serializers.SerializerMethodField()

    class Meta:
        model = Bill
        fields = [
            "id",
            "name",
            "payee",
            "category",
            "property",
            "recurring",
            "amount_due",
            "amount_paid",
            "balance",
            "due_date",
            "status",
            "display_status",
            "paid_on",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["recurring", "amount_paid", "status", "paid_on"]

    def get_display_status(self, bill) -> str:
        return bill.display_status()

    def validate_amount_due(self, value):
        if self.instance and value < self.instance.amount_paid:
            raise serializers.ValidationError(
                f"Cannot be less than the {self.instance.amount_paid} already paid."
            )
        return value


class BillViewSet(HouseholdScopedViewSet):
    """Bills. Filters: ``?status=open|overdue|due_soon|paid``, ``?due_after``,
    ``?due_before`` (ISO dates), ``?category``, ``?property``, ``?search``."""

    serializer_class = BillSerializer
    queryset = Bill.objects.select_related("category", "property")

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        today = timezone.localdate()
        status_filter = params.get("status")
        if status_filter == "open":
            qs = qs.open()
        elif status_filter == "overdue":
            qs = qs.overdue(today)
        elif status_filter == "due_soon":
            qs = qs.due_soon(today)
        elif status_filter == "paid":
            qs = qs.filter(status="paid")
        for param, lookup in (("due_after", "due_date__gte"), ("due_before", "due_date__lte")):
            if value := params.get(param):
                try:
                    qs = qs.filter(**{lookup: date.fromisoformat(value)})
                except ValueError as exc:
                    raise serializers.ValidationError({param: "Use YYYY-MM-DD."}) from exc
        for param in ("category", "property"):
            if params.get(param, "").isdigit():
                qs = qs.filter(**{f"{param}_id": params[param]})
        if search := params.get("search"):
            qs = qs.filter(Q(name__icontains=search) | Q(payee__icontains=search))
        return qs

    def perform_create(self, serializer):
        bill = Bill(household=self.household, **serializer.validated_data)
        serializer.instance = services.save_bill(bill=bill, actor=self.request.user)

    def perform_update(self, serializer):
        bill = serializer.instance
        for field, value in serializer.validated_data.items():
            setattr(bill, field, value)
        serializer.instance = services.save_bill(bill=bill, actor=self.request.user)

    def perform_destroy(self, instance):
        try:
            services.delete_bill(bill=instance, actor=self.request.user)
        except ValidationError as exc:
            raise_drf(exc)

    @action(detail=True, methods=["get", "post"], serializer_class=PaymentSerializer)
    def payments(self, request, household_pk=None, pk=None):
        """GET: this bill's payments. POST: record a (partial) payment."""
        bill = self.get_object()
        if request.method == "GET":
            data = PaymentSerializer(bill.payments.all(), many=True).data
            return Response(data)
        serializer = PaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payment = payment_services.record_payment(
                bill=bill, recorded_by=request.user, **serializer.validated_data
            )
        except ValidationError as exc:
            raise_drf(exc)
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class RecurringBillSerializer(HouseholdScopedSerializer):
    household_scoped_fields = ("property",)
    category = CategoryRelatedField()

    class Meta:
        model = RecurringBill
        fields = [
            "id",
            "name",
            "payee",
            "category",
            "property",
            "amount",
            "frequency",
            "start_date",
            "end_date",
            "is_active",
            "autopay",
            "notes",
            "generated_through",
        ]
        read_only_fields = ["generated_through"]

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "Must be on or after start_date."})
        return attrs


class RecurringBillViewSet(HouseholdScopedViewSet):
    serializer_class = RecurringBillSerializer
    queryset = RecurringBill.objects.select_related("category", "property")

    def perform_create(self, serializer):
        schedule = RecurringBill(household=self.household, **serializer.validated_data)
        services.save_recurring_bill(schedule=schedule, actor=self.request.user)
        serializer.instance = schedule

    def perform_update(self, serializer):
        schedule = serializer.instance
        for field, value in serializer.validated_data.items():
            setattr(schedule, field, value)
        services.save_recurring_bill(schedule=schedule, actor=self.request.user)

    def perform_destroy(self, instance):
        services.delete_recurring_bill(schedule=instance, actor=self.request.user)
