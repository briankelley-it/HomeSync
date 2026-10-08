from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.bills.api import CategoryRelatedField
from apps.core.api import HouseholdRolePermission, HouseholdScopedSerializer, HouseholdScopedViewSet
from apps.households.models import Role

from . import analytics
from .models import Budget, Expense, IncomeSource


class ExpenseSerializer(HouseholdScopedSerializer):
    household_scoped_fields = ("property",)
    category = CategoryRelatedField()

    class Meta:
        model = Expense
        fields = ["id", "description", "amount", "spent_on", "category", "property", "notes"]


class ExpenseViewSet(HouseholdScopedViewSet):
    serializer_class = ExpenseSerializer
    queryset = Expense.objects.select_related("category", "property")

    def perform_create(self, serializer):
        serializer.save(household=self.household, recorded_by=self.request.user)


class BudgetSerializer(HouseholdScopedSerializer):
    household_scoped_fields = ("property",)
    category = CategoryRelatedField()

    class Meta:
        model = Budget
        fields = ["id", "category", "property", "amount"]
        validators = []  # uniqueness is checked against the household below

    def validate(self, attrs):
        category = attrs.get("category", getattr(self.instance, "category", None))
        prop = attrs.get("property", getattr(self.instance, "property", None))
        clash = Budget.objects.filter(
            household=self.context["household"], category=category, property=prop
        )
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("A budget for this category already exists.")
        return attrs


class BudgetViewSet(HouseholdScopedViewSet):
    serializer_class = BudgetSerializer
    queryset = Budget.objects.select_related("category", "property")
    write_role = Role.ADMIN


class IncomeSourceSerializer(HouseholdScopedSerializer):
    household_scoped_fields = ("earner",)
    monthly_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = IncomeSource
        fields = ["id", "name", "amount", "frequency", "earner", "is_active", "monthly_amount"]


class IncomeSourceViewSet(HouseholdScopedViewSet):
    serializer_class = IncomeSourceSerializer
    queryset = IncomeSource.objects.all()
    write_role = Role.ADMIN


class SummaryView(APIView):
    """Dashboard numbers for the current month (amounts are decimal strings)."""

    permission_classes = [HouseholdRolePermission]

    def get(self, request, household_pk):
        summary = analytics.dashboard_summary(self.household, timezone.localdate())
        money = (
            "bills_this_month",
            "paid_this_month",
            "due_soon_total",
            "overdue_total",
            "outstanding",
            "income",
            "expenses_this_month",
            "remaining_budget",
        )
        data = {key: str(getattr(summary, key)) for key in money}
        data.update(
            month_start=summary.month_start,
            month_end=summary.month_end,
            bills_this_month_count=summary.bills_this_month_count,
            due_soon_count=summary.due_soon_count,
            overdue_count=summary.overdue_count,
            currency=self.household.currency,
            trend=[
                {"month": m["month"], "bills": str(m["bills"]), "other": str(m["other"])}
                for m in summary.trend
            ],
            categories=[{"name": c["name"], "total": str(c["total"])} for c in summary.categories],
        )
        return Response(data)
