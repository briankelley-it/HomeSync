from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("", views.PaymentListView.as_view(), name="list"),
    path("export.csv", views.PaymentExportView.as_view(), name="export"),
    path("bill/<int:bill_pk>/record/", views.RecordPaymentView.as_view(), name="record"),
    path("<int:pk>/delete/", views.DeletePaymentView.as_view(), name="delete"),
]
