from django.contrib import admin

from .models import Bill, Category, RecurringBill


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "household", "color"]
    search_fields = ["name"]


@admin.register(RecurringBill)
class RecurringBillAdmin(admin.ModelAdmin):
    list_display = ["name", "household", "amount", "frequency", "start_date", "is_active"]
    list_filter = ["frequency", "is_active"]
    readonly_fields = ["generated_through"]


@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = ["name", "household", "amount_due", "amount_paid", "due_date", "status"]
    list_filter = ["status", "category"]
    search_fields = ["name", "payee"]
    date_hierarchy = "due_date"
    readonly_fields = ["amount_paid", "status", "paid_on"]
