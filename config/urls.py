from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("households/", include("apps.households.urls")),
    path("bills/", include("apps.bills.urls")),
    path("payments/", include("apps.payments.urls")),
    path("properties/", include("apps.properties.urls")),
    path("budgets/", include("apps.budgets.urls")),
    path("documents/", include("apps.documents.urls")),
    path("", include("apps.core.urls")),
]
