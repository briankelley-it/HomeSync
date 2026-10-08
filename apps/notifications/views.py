from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import UpdateView

from .forms import NotificationPreferenceForm
from .models import NotificationPreference, ReminderLog


class PreferencesView(LoginRequiredMixin, UpdateView):
    form_class = NotificationPreferenceForm
    template_name = "notifications/preferences.html"
    success_url = reverse_lazy("notifications:preferences")

    def get_object(self, queryset=None):
        return NotificationPreference.for_user(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["recent_reminders"] = ReminderLog.objects.filter(
            user=self.request.user
        ).select_related("bill", "bill__household")[:10]
        return context

    def form_valid(self, form):
        messages.success(self.request, "Notification preferences saved.")
        return super().form_valid(form)
