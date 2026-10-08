from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.generic import TemplateView

from apps.bills.models import Bill
from apps.budgets import analytics
from apps.households.permissions import HouseholdMixin


class DashboardView(HouseholdMixin, TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        summary = analytics.dashboard_summary(self.household, today)
        bills = Bill.objects.filter(household=self.household).select_related("category", "property")
        context.update(
            today=today,
            summary=summary,
            chart_data=analytics.chart_payload(summary),
            overdue_bills=bills.overdue(today).order_by("due_date")[:5],
            upcoming_bills=bills.open().filter(due_date__gte=today).order_by("due_date")[:6],
            recent_activity=self.household.activity.select_related("actor")[:8],
            has_bills=bills.exists(),
        )
        return context


def health(request):
    """Liveness/readiness probe used by Docker and load balancers."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok"})


def ratelimited(request, exception=None):
    return render(request, "429.html", status=429)
