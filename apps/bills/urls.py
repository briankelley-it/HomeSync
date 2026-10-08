from django.urls import path

from . import views

app_name = "bills"

urlpatterns = [
    path("", views.BillListView.as_view(), name="list"),
    path("new/", views.BillCreateView.as_view(), name="create"),
    path("<int:pk>/", views.BillDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.BillUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", views.BillDeleteView.as_view(), name="delete"),
    path("calendar/", views.CalendarView.as_view(), name="calendar"),
    path("recurring/", views.RecurringListView.as_view(), name="recurring_list"),
    path("recurring/new/", views.RecurringCreateView.as_view(), name="recurring_create"),
    path("recurring/<int:pk>/", views.RecurringDetailView.as_view(), name="recurring_detail"),
    path("recurring/<int:pk>/edit/", views.RecurringUpdateView.as_view(), name="recurring_update"),
    path(
        "recurring/<int:pk>/delete/", views.RecurringDeleteView.as_view(), name="recurring_delete"
    ),
    path("categories/", views.CategoryListView.as_view(), name="category_list"),
    path("categories/new/", views.CategoryCreateView.as_view(), name="category_create"),
    path("categories/<int:pk>/edit/", views.CategoryUpdateView.as_view(), name="category_update"),
    path("categories/<int:pk>/delete/", views.CategoryDeleteView.as_view(), name="category_delete"),
]
