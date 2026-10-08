from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.PreferencesView.as_view(), name="preferences"),
]
