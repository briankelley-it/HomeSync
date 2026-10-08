from django.contrib import admin

from .models import NotificationPreference, ReminderLog


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ["user", "email_reminders", "remind_days_before", "overdue_alerts"]


@admin.register(ReminderLog)
class ReminderLogAdmin(admin.ModelAdmin):
    list_display = ["bill", "user", "kind", "sent_at"]
    list_filter = ["kind"]
