from django.contrib import admin

from .models import Budget, Expense, IncomeSource


@admin.register(IncomeSource)
class IncomeSourceAdmin(admin.ModelAdmin):
    list_display = ["name", "household", "amount", "frequency", "is_active"]


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ["category", "property", "household", "amount"]


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ["description", "household", "category", "amount", "spent_on"]
    date_hierarchy = "spent_on"
