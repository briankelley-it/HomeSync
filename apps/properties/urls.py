from django.urls import path

from . import views

app_name = "properties"

urlpatterns = [
    path("", views.PropertyListView.as_view(), name="list"),
    path("new/", views.PropertyCreateView.as_view(), name="create"),
    path("<int:pk>/", views.PropertyDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.PropertyUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", views.PropertyDeleteView.as_view(), name="delete"),
]
