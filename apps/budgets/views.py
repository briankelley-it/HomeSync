from datetime import date

from dateutil.relativedelta import relativedelta
from django.contrib import messages
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from apps.core.mixins import FormPageMixin, HouseholdDeleteView, htmx_redirect
from apps.households.permissions import (
    HouseholdEditMixin,
    HouseholdFormMixin,
    HouseholdManageMixin,
    HouseholdMixin,
)

from . import analytics
from .forms import BudgetForm, ExpenseForm, IncomeSourceForm
from .models import Budget, Expense, IncomeSource


class AnalyticsView(HouseholdMixin, TemplateView):
    template_name = "budgets/analytics.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        prop = None
        prop_id = self.request.GET.get("property", "")
        if prop_id.isdigit():
            prop = self.household.properties.filter(pk=prop_id).first()

        this_start, this_end = analytics.month_bounds(today)
        last_start, last_end = analytics.month_bounds(today - relativedelta(months=1))
        this_month = analytics.category_breakdown(self.household, this_start, this_end, prop)
        last_month = analytics.category_breakdown(self.household, last_start, last_end, prop)
        trend = analytics.spending_trend(self.household, today, months=12, prop=prop)

        # Month-over-month comparison per category (union of both months).
        names = {c["name"]: c["color"] for c in this_month + last_month}
        this_by = {c["name"]: c["total"] for c in this_month}
        last_by = {c["name"]: c["total"] for c in last_month}
        summary = analytics.dashboard_summary(self.household, today, prop=prop)

        context.update(
            summary=summary,
            selected_property=prop,
            properties=self.household.properties.all(),
            budgets=analytics.budget_progress(self.household, today),
            this_month=this_month,
            this_month_label=today.strftime("%B %Y"),
            last_month_label=(today - relativedelta(months=1)).strftime("%B %Y"),
            chart_data={
                "trend": {
                    "labels": [m["label"] for m in trend],
                    "bills": [str(m["bills"]) for m in trend],
                    "other": [str(m["other"]) for m in trend],
                },
                "categories": analytics.chart_payload(summary)["categories"],
                "comparison": {
                    "labels": list(names),
                    "this": [str(this_by.get(n, 0)) for n in names],
                    "last": [str(last_by.get(n, 0)) for n in names],
                },
            },
        )
        return context


class BudgetOverviewView(HouseholdMixin, TemplateView):
    """Budgets with progress, income sources, and recent one-off expenses."""

    template_name = "budgets/overview.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        summary = analytics.dashboard_summary(self.household, today)
        context.update(
            summary=summary,
            budgets=analytics.budget_progress(self.household, today),
            income_sources=self.household.income_sources.select_related("earner__user"),
            expenses=self.household.expenses.select_related("category", "property")[:10],
            month_label=today.strftime("%B %Y"),
        )
        return context


class ExpenseListView(HouseholdMixin, ListView):
    model = Expense
    template_name = "budgets/expense_list.html"
    paginate_by = 30

    def get_queryset(self):
        qs = super().get_queryset().select_related("category", "property", "recorded_by")
        month = self.request.GET.get("month", "")
        try:
            start = date.fromisoformat(f"{month}-01")
        except ValueError:
            return qs
        return qs.filter(spent_on__range=analytics.month_bounds(start))


# ----- CRUD ---------------------------------------------------------------- #
class _BaseForm(HouseholdFormMixin, FormPageMixin):
    success_url = reverse_lazy("budgets:budget_list")
    noun = "item"

    def form_valid(self, form):
        form.instance.household = self.household
        if hasattr(form.instance, "recorded_by_id") and not form.instance.recorded_by_id:
            form.instance.recorded_by = self.request.user
        self.object = form.save()
        messages.success(self.request, f"Saved {self.noun}.")
        return htmx_redirect(self.request, str(self.get_success_url()))


class BudgetCreateView(HouseholdManageMixin, _BaseForm, CreateView):
    model, form_class, page_title, noun = Budget, BudgetForm, "New budget", "budget"


class BudgetUpdateView(HouseholdManageMixin, _BaseForm, UpdateView):
    model, form_class, page_title, noun = Budget, BudgetForm, "Edit budget", "budget"


class BudgetDeleteView(HouseholdManageMixin, HouseholdDeleteView):
    model, object_label = Budget, "budget"
    success_url = reverse_lazy("budgets:budget_list")


class IncomeCreateView(HouseholdManageMixin, _BaseForm, CreateView):
    model, form_class, page_title, noun = IncomeSource, IncomeSourceForm, "Add income", "income"


class IncomeUpdateView(HouseholdManageMixin, _BaseForm, UpdateView):
    model, form_class, page_title, noun = IncomeSource, IncomeSourceForm, "Edit income", "income"


class IncomeDeleteView(HouseholdManageMixin, HouseholdDeleteView):
    model, object_label = IncomeSource, "income source"
    success_url = reverse_lazy("budgets:budget_list")


class ExpenseCreateView(HouseholdEditMixin, _BaseForm, CreateView):
    model, form_class, page_title, noun = Expense, ExpenseForm, "Record an expense", "expense"
    success_url = reverse_lazy("budgets:expense_list")


class ExpenseUpdateView(HouseholdEditMixin, _BaseForm, UpdateView):
    model, form_class, page_title, noun = Expense, ExpenseForm, "Edit expense", "expense"
    success_url = reverse_lazy("budgets:expense_list")


class ExpenseDeleteView(HouseholdDeleteView):
    model, object_label = Expense, "expense"
    success_url = reverse_lazy("budgets:expense_list")
