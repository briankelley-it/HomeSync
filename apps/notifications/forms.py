from django import forms

from .models import NotificationPreference


class NotificationPreferenceForm(forms.ModelForm):
    class Meta:
        model = NotificationPreference
        fields = ("email_reminders", "remind_days_before", "overdue_alerts")
        widgets = {"remind_days_before": forms.NumberInput(attrs={"min": 0, "max": 30})}
