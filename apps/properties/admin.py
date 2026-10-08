from django.contrib import admin

from .models import Property


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ["name", "household", "property_type", "city", "is_primary"]
    list_filter = ["property_type"]
    search_fields = ["name", "address_line1", "city"]
