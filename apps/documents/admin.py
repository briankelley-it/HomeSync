from django.contrib import admin

from .models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["title", "household", "kind", "content_type", "size", "created_at"]
    list_filter = ["kind", "content_type"]
    readonly_fields = ["original_filename", "content_type", "size"]
