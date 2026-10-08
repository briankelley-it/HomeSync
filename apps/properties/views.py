from decimal import Decimal

from django.contrib import messages
from django.db.models import Count, DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.budgets.analytics import dashboard_summary
from apps.core.mixins import FormPageMixin, HouseholdDeleteView, htmx_redirect
from apps.households.permissions import HouseholdFormMixin, HouseholdManageMixin, HouseholdMixin
from apps.households.services import log_activity

from .forms import PropertyForm
from .models import Property

OPEN = ~Q(bills__status="paid")


class PropertyListView(HouseholdMixin, ListView):
    model = Property
    template_name = "properties/property_list.html"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .annotate(
                open_bills=Count("bills", filter=OPEN),
                open_balance=Coalesce(
                    Sum(F("bills__amount_due") - F("bills__amount_paid"), filter=OPEN),
                    Value(Decimal("0.00")),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
            )
            .prefetch_related("members__user")
        )


class PropertyDetailView(HouseholdMixin, DetailView):
    model = Property
    template_name = "properties/property_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        prop = self.object
        today = timezone.localdate()
        context.update(
            summary=dashboard_summary(self.household, today, prop=prop),
            upcoming=prop.bills.open().select_related("category").order_by("due_date")[:10],
            recurring=prop.recurring_bills.filter(is_active=True),
            expenses=prop.expenses.select_related("category")[:5],
            budgets=prop.budgets.select_related("category"),
            documents=prop.documents.all()[:5],
            members=prop.members.select_related("user"),
            today=today,
        )
        return context


class PropertyFormMixin(HouseholdManageMixin, HouseholdFormMixin, FormPageMixin):
    model = Property
    form_class = PropertyForm
    submit_label = "Save property"
    success_url = reverse_lazy("properties:list")

    def form_valid(self, form):
        creating = form.instance.pk is None
        form.instance.household = self.household
        prop = form.save()
        if prop.is_primary:
            # Only one primary residence per household.
            self.household.properties.exclude(pk=prop.pk).update(is_primary=False)
        verb = "added" if creating else "updated"
        log_activity(self.household, self.request.user, verb, f"Property {prop.name} {verb}")
        messages.success(self.request, f"Saved {prop.name}.")
        return htmx_redirect(self.request, prop.get_absolute_url())


class PropertyCreateView(PropertyFormMixin, CreateView):
    page_title = "Add a property"


class PropertyUpdateView(PropertyFormMixin, UpdateView):
    page_title = "Edit property"


class PropertyDeleteView(HouseholdManageMixin, HouseholdDeleteView):
    model = Property
    object_label = "property"
    success_url = reverse_lazy("properties:list")
