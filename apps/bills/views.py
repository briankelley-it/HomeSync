import calendar
from collections import defaultdict
from datetime import date

from dateutil.relativedelta import relativedelta
from django.contrib import messages
from django.db.models import Q, Sum
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from apps.core.mixins import FormPageMixin, HouseholdDeleteView, htmx_redirect, is_htmx
from apps.households.permissions import (
    HouseholdEditMixin,
    HouseholdFormMixin,
    HouseholdManageMixin,
    HouseholdMixin,
)
from apps.payments.forms import PaymentForm

from . import services
from .forms import BillForm, CategoryForm, RecurringBillForm
from .models import Bill, Category, RecurringBill

# --------------------------------------------------------------------------- #
# Bills
# --------------------------------------------------------------------------- #
STATUS_FILTERS = {
    "open": lambda qs, today: qs.open(),
    "overdue": lambda qs, today: qs.overdue(today),
    "due_soon": lambda qs, today: qs.due_soon(today),
    "paid": lambda qs, today: qs.filter(status="paid"),
    "all": lambda qs, today: qs,
}


class BillListView(HouseholdMixin, ListView):
    model = Bill
    template_name = "bills/bill_list.html"
    paginate_by = 25

    def get_queryset(self):
        today = timezone.localdate()
        qs = super().get_queryset().select_related("category", "property")
        params = self.request.GET
        self.status = params.get("status") if params.get("status") in STATUS_FILTERS else "open"
        qs = STATUS_FILTERS[self.status](qs, today)
        if params.get("category", "").isdigit():
            qs = qs.filter(category_id=params["category"])
        if params.get("property", "").isdigit():
            qs = qs.filter(property_id=params["property"])
        if q := params.get("q", "").strip():
            qs = qs.filter(Q(name__icontains=q) | Q(payee__icontains=q))
        if self.status in ("paid", "all"):
            qs = qs.order_by("-due_date", "name")
        return qs

    def get_template_names(self):
        if is_htmx(self.request) and self.request.headers.get("HX-Target") == "bill-table":
            return ["bills/partials/bill_table.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        totals = self.object_list.aggregate(due=Sum("amount_due"), paid=Sum("amount_paid"))
        context.update(
            status=self.status,
            status_choices=[
                ("open", "Open"),
                ("due_soon", "Due soon"),
                ("overdue", "Overdue"),
                ("paid", "Paid"),
                ("all", "All"),
            ],
            categories=Category.objects.for_household(self.household),
            properties=self.household.properties.all(),
            filtered_balance=(totals["due"] or 0) - (totals["paid"] or 0),
            today=timezone.localdate(),
        )
        return context


class BillDetailView(HouseholdMixin, DetailView):
    model = Bill
    template_name = "bills/bill_detail.html"

    def get_queryset(self):
        return super().get_queryset().select_related("category", "property", "recurring")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        bill = self.object
        context["payments"] = bill.payments.select_related("recorded_by")
        context["documents"] = bill.documents.all()
        if self.membership.can_edit and not bill.is_paid:
            context["payment_form"] = PaymentForm(bill=bill)
        return context


class BillFormMixin(HouseholdEditMixin, HouseholdFormMixin, FormPageMixin):
    model = Bill
    form_class = BillForm
    submit_label = "Save bill"

    def form_valid(self, form):
        bill = form.save(commit=False)
        bill.household = self.household
        services.save_bill(bill=bill, actor=self.request.user)
        messages.success(self.request, f"Saved {bill.name}.")
        return htmx_redirect(self.request, bill.get_absolute_url())


class BillCreateView(BillFormMixin, CreateView):
    page_title = "Add a bill"
    success_url = reverse_lazy("bills:list")

    def get_initial(self):
        initial = super().get_initial()
        if due := self.request.GET.get("due_date"):
            initial["due_date"] = due
        return initial


class BillUpdateView(BillFormMixin, UpdateView):
    page_title = "Edit bill"

    def get_success_url(self):
        return self.object.get_absolute_url()


class BillDeleteView(HouseholdDeleteView):
    model = Bill
    object_label = "bill"
    success_url = reverse_lazy("bills:list")

    def perform_delete(self, obj):
        services.delete_bill(bill=obj, actor=self.request.user)

    def get_error_url(self, obj):
        return obj.get_absolute_url()


# --------------------------------------------------------------------------- #
# Recurring schedules
# --------------------------------------------------------------------------- #
class RecurringListView(HouseholdMixin, ListView):
    model = RecurringBill
    template_name = "bills/recurring_list.html"

    def get_queryset(self):
        return super().get_queryset().select_related("category", "property")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["monthly_equivalent"] = services.monthly_recurring_total(self.household)
        return context


class RecurringDetailView(HouseholdMixin, DetailView):
    model = RecurringBill
    template_name = "bills/recurring_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["bills"] = self.object.bills.order_by("-due_date")[:24]
        return context


class RecurringFormMixin(HouseholdEditMixin, HouseholdFormMixin, FormPageMixin):
    model = RecurringBill
    form_class = RecurringBillForm
    submit_label = "Save schedule"
    success_url = reverse_lazy("bills:recurring_list")

    def form_valid(self, form):
        schedule = form.save(commit=False)
        schedule.household = self.household
        created = services.save_recurring_bill(schedule=schedule, actor=self.request.user)
        messages.success(
            self.request,
            f"Saved {schedule.name}. {created} upcoming bill(s) scheduled.",
        )
        return htmx_redirect(self.request, schedule.get_absolute_url())


class RecurringCreateView(RecurringFormMixin, CreateView):
    page_title = "New recurring bill"


class RecurringUpdateView(RecurringFormMixin, UpdateView):
    page_title = "Edit recurring bill"


class RecurringDeleteView(HouseholdDeleteView):
    model = RecurringBill
    object_label = "recurring bill"
    success_url = reverse_lazy("bills:recurring_list")

    def perform_delete(self, obj):
        services.delete_recurring_bill(schedule=obj, actor=self.request.user)


# --------------------------------------------------------------------------- #
# Categories (built-ins are read-only; custom ones are household-managed)
# --------------------------------------------------------------------------- #
class CategoryListView(HouseholdMixin, ListView):
    model = Category
    template_name = "bills/category_list.html"

    def get_queryset(self):
        return Category.objects.for_household(self.household)


class CategoryFormMixin(HouseholdManageMixin, HouseholdFormMixin, FormPageMixin):
    model = Category
    form_class = CategoryForm
    success_url = reverse_lazy("bills:category_list")
    submit_label = "Save category"

    def get_queryset(self):
        return Category.objects.filter(household=self.household)

    def form_valid(self, form):
        form.instance.household = self.household
        form.save()
        messages.success(self.request, f"Saved category {form.instance.name}.")
        return htmx_redirect(self.request, str(self.success_url))


class CategoryCreateView(CategoryFormMixin, CreateView):
    page_title = "New category"


class CategoryUpdateView(CategoryFormMixin, UpdateView):
    page_title = "Edit category"


class CategoryDeleteView(HouseholdManageMixin, HouseholdDeleteView):
    model = Category
    object_label = "category"
    success_url = reverse_lazy("bills:category_list")

    def get_queryset(self):
        return Category.objects.filter(household=self.household)


# --------------------------------------------------------------------------- #
# Calendar
# --------------------------------------------------------------------------- #
class CalendarView(HouseholdMixin, TemplateView):
    template_name = "bills/calendar.html"

    def get_month(self) -> date:
        today = timezone.localdate()
        try:
            year = int(self.request.GET.get("year", today.year))
            month = int(self.request.GET.get("month", today.month))
            return date(year, month, 1)
        except ValueError:
            return today.replace(day=1)

    def get_template_names(self):
        if is_htmx(self.request):
            return ["bills/partials/calendar_grid.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        month = self.get_month()
        weeks = calendar.Calendar(firstweekday=6).monthdatescalendar(month.year, month.month)
        bills = (
            Bill.objects.filter(
                household=self.household, due_date__range=(weeks[0][0], weeks[-1][-1])
            )
            .select_related("category")
            .order_by("due_date", "name")
        )
        by_day = defaultdict(list)
        for bill in bills:
            by_day[bill.due_date].append(bill)
        today = timezone.localdate()
        in_month = [b for b in bills if b.due_date.month == month.month]
        prev_month, next_month = month - relativedelta(months=1), month + relativedelta(months=1)
        context.update(
            month=month,
            today=today,
            weekdays=["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
            weeks=[[(day, by_day.get(day, [])) for day in week] for week in weeks],
            prev_url=f"{reverse('bills:calendar')}?year={prev_month.year}&month={prev_month.month}",
            next_url=f"{reverse('bills:calendar')}?year={next_month.year}&month={next_month.month}",
            today_url=reverse("bills:calendar"),
            month_total=sum((b.amount_due for b in in_month), 0),
            month_paid=sum((b.amount_paid for b in in_month), 0),
            month_count=len(in_month),
        )
        return context
