import csv
from datetime import date

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views import View
from django.views.generic import ListView

from apps.bills.models import Bill, Category
from apps.core.mixins import htmx_redirect, is_htmx
from apps.households.permissions import HouseholdEditMixin, HouseholdMixin

from . import services
from .forms import PaymentForm
from .models import Payment, PaymentMethod


def _parse_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


class PaymentFilterMixin:
    """Shared filtering for the payment history page and CSV export."""

    def filtered_payments(self):
        params = self.request.GET
        qs = Payment.objects.filter(household=self.household).select_related(
            "bill", "bill__category", "bill__property", "recorded_by"
        )
        if start := _parse_date(params.get("start")):
            qs = qs.filter(paid_on__gte=start)
        if end := _parse_date(params.get("end")):
            qs = qs.filter(paid_on__lte=end)
        if params.get("method") in PaymentMethod.values:
            qs = qs.filter(method=params["method"])
        if params.get("category", "").isdigit():
            qs = qs.filter(bill__category_id=params["category"])
        if params.get("property", "").isdigit():
            qs = qs.filter(bill__property_id=params["property"])
        return qs


class PaymentListView(HouseholdMixin, PaymentFilterMixin, ListView):
    template_name = "payments/payment_list.html"
    paginate_by = 30

    def get_queryset(self):
        return self.filtered_payments()

    def get_template_names(self):
        if is_htmx(self.request) and self.request.headers.get("HX-Target") == "payment-table":
            return ["payments/partials/payment_table.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            filtered_total=self.object_list.aggregate(t=Sum("amount"))["t"] or 0,
            outstanding=services.outstanding_total(self.household),
            methods=PaymentMethod.choices,
            categories=Category.objects.for_household(self.household),
            properties=self.household.properties.all(),
            querystring=self.request.GET.urlencode(),
        )
        return context


class PaymentExportView(HouseholdMixin, PaymentFilterMixin, View):
    """Download the (filtered) payment history as CSV."""

    def get(self, request):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="houseledger-payments.csv"'
        writer = csv.writer(response)
        writer.writerow(
            ["Paid on", "Bill", "Category", "Property", "Amount", "Method", "Reference", "By"]
        )
        for p in self.filtered_payments().iterator():
            writer.writerow(
                [
                    p.paid_on.isoformat(),
                    _csv_safe(p.bill.name),
                    _csv_safe(p.bill.category.name),
                    _csv_safe(p.bill.property.name if p.bill.property else ""),
                    str(p.amount),
                    p.get_method_display(),
                    _csv_safe(p.reference),
                    _csv_safe(p.recorded_by.email if p.recorded_by else ""),
                ]
            )
        return response


def _csv_safe(value: str) -> str:
    """Neutralize spreadsheet formula injection (cells starting with = + - @)."""
    return f"'{value}" if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


class RecordPaymentView(HouseholdEditMixin, View):
    """Record a payment for a bill. Works as a page or as an HTMX dialog."""

    template_name = "payments/record_payment.html"

    def get_bill(self):
        return get_object_or_404(Bill, pk=self.kwargs["bill_pk"], household=self.household)

    def render_form(self, form, bill, status=200):
        template = (
            "payments/partials/payment_form.html" if is_htmx(self.request) else (self.template_name)
        )
        return render(self.request, template, {"form": form, "bill": bill}, status=status)

    def get(self, request, bill_pk):
        return self.render_form(PaymentForm(bill=self.get_bill()), self.get_bill())

    def post(self, request, bill_pk):
        bill = self.get_bill()
        form = PaymentForm(request.POST, bill=bill)
        if form.is_valid():
            try:
                services.record_payment(bill=bill, recorded_by=request.user, **form.cleaned_data)
            except ValidationError as exc:
                for field, errors in exc.message_dict.items():
                    for error in errors:
                        form.add_error(field if field in form.fields else None, error)
            else:
                messages.success(request, f"Payment recorded for {bill.name}.")
                return htmx_redirect(request, bill.get_absolute_url())
        return self.render_form(form, bill)


class DeletePaymentView(HouseholdEditMixin, View):
    def post(self, request, pk):
        payment = get_object_or_404(Payment, pk=pk, household=self.household)
        bill = services.delete_payment(payment=payment, actor=request.user)
        messages.success(request, "Payment removed.")
        return htmx_redirect(request, bill.get_absolute_url())
