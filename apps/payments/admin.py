from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["bill", "household", "amount", "paid_on", "method", "recorded_by"]
    list_filter = ["method"]
    date_hierarchy = "paid_on"
    raw_id_fields = ["bill"]

    def has_change_permission(self, request, obj=None):
        # Payments change bill totals; edit through the app so totals stay in sync.
        return False
