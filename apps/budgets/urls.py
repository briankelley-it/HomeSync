from django.urls import path

from . import views

app_name = "budgets"

urlpatterns = [
    path("", views.BudgetOverviewView.as_view(), name="budget_list"),
    path("analytics/", views.AnalyticsView.as_view(), name="analytics"),
    path("new/", views.BudgetCreateView.as_view(), name="budget_create"),
    path("<int:pk>/edit/", views.BudgetUpdateView.as_view(), name="budget_update"),
    path("<int:pk>/delete/", views.BudgetDeleteView.as_view(), name="budget_delete"),
    path("income/new/", views.IncomeCreateView.as_view(), name="income_create"),
    path("income/<int:pk>/edit/", views.IncomeUpdateView.as_view(), name="income_update"),
    path("income/<int:pk>/delete/", views.IncomeDeleteView.as_view(), name="income_delete"),
    path("expenses/", views.ExpenseListView.as_view(), name="expense_list"),
    path("expenses/new/", views.ExpenseCreateView.as_view(), name="expense_create"),
    path("expenses/<int:pk>/edit/", views.ExpenseUpdateView.as_view(), name="expense_update"),
    path("expenses/<int:pk>/delete/", views.ExpenseDeleteView.as_view(), name="expense_delete"),
]
