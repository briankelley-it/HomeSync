from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render
from django.views.generic import TemplateView

from apps.households.permissions import HouseholdMixin


class DashboardView(HouseholdMixin, TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["recent_activity"] = self.household.activity.select_related("actor")[:8]
        return context


def health(request):
    """Liveness/readiness probe used by Docker and load balancers."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok"})


def ratelimited(request, exception=None):
    return render(request, "429.html", status=429)
