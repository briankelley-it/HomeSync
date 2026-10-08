"""REST API v1 routes. Household resources are nested under the household id."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.bills.api import BillViewSet, CategoryViewSet, RecurringBillViewSet
from apps.budgets.api import BudgetViewSet, ExpenseViewSet, IncomeSourceViewSet, SummaryView
from apps.households.api import HouseholdViewSet
from apps.payments.api import PaymentViewSet
from apps.properties.api import PropertyViewSet

router = DefaultRouter()
router.register("households", HouseholdViewSet, basename="household")

nested = DefaultRouter()
nested.include_root_view = False
nested.register("bills", BillViewSet, basename="bill")
nested.register("recurring-bills", RecurringBillViewSet, basename="recurring-bill")
nested.register("payments", PaymentViewSet, basename="payment")
nested.register("categories", CategoryViewSet, basename="category")
nested.register("properties", PropertyViewSet, basename="property")
nested.register("expenses", ExpenseViewSet, basename="expense")
nested.register("budgets", BudgetViewSet, basename="budget")
nested.register("income-sources", IncomeSourceViewSet, basename="income-source")

app_name = "api"

urlpatterns = [
    path("", include(router.urls)),
    path("households/<int:household_pk>/", include(nested.urls)),
    path("households/<int:household_pk>/summary/", SummaryView.as_view(), name="summary"),
]
