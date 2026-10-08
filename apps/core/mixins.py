"""Reusable view building blocks.

Forms render as a normal page, or as a dialog when the request comes from HTMX
(``HX-Request`` header). Links keep a real ``href`` so everything also works
without JavaScript.
"""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError, RestrictedError
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import DeleteView
from django.views.generic.edit import FormMixin

from apps.households.permissions import HouseholdEditMixin


def safe_next(request, default: str = "") -> str:
    """Return ``?next=`` only if it points at this site (blocks open redirects)."""
    candidate = request.GET.get("next", "")
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return default


def is_htmx(request) -> bool:
    return request.headers.get("HX-Request") == "true"


def htmx_redirect(request, url: str):
    """Redirect that also works for HTMX requests (full page navigation)."""
    if is_htmx(request):
        return HttpResponse(status=204, headers={"HX-Redirect": url})
    return redirect(url)


class FormPageMixin(FormMixin):
    page_title = ""
    submit_label = "Save"
    form_template_name = "core/form_page.html"

    def get_template_names(self):
        if is_htmx(self.request):
            return ["partials/form_modal.html"]
        return [self.template_name or self.form_template_name]

    def get_page_title(self) -> str:
        return self.page_title

    def get_cancel_url(self) -> str:
        obj = getattr(self, "object", None)
        if obj is not None and hasattr(obj, "get_absolute_url"):
            default = obj.get_absolute_url()
        else:
            default = str(getattr(self, "success_url", None) or "/")
        return safe_next(self.request, default)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            page_title=self.get_page_title(),
            submit_label=self.submit_label,
            cancel_url=self.get_cancel_url(),
            form_action=self.request.get_full_path(),
        )
        return context


class HouseholdDeleteView(HouseholdEditMixin, DeleteView):
    """Confirm-then-delete with friendly errors for protected records.

    Override ``perform_delete`` to route deletion through a service.
    """

    template_name = "core/confirm_delete.html"
    object_label = "item"
    success_message = "{label} deleted."

    def get_template_names(self):
        if is_htmx(self.request):
            return ["partials/confirm_delete_modal.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["object_label"] = self.object_label
        context["cancel_url"] = safe_next(self.request, self.get_success_url())
        return context

    def perform_delete(self, obj) -> None:
        obj.delete()

    def form_valid(self, form):
        obj = self.object
        try:
            self.perform_delete(obj)
        except ValidationError as exc:
            messages.error(self.request, exc.messages[0])
            return htmx_redirect(self.request, self.get_error_url(obj))
        except (ProtectedError, RestrictedError):
            messages.error(
                self.request,
                f"This {self.object_label} is still in use and cannot be deleted.",
            )
            return htmx_redirect(self.request, self.get_error_url(obj))
        messages.success(self.request, self.success_message.format(label=str(obj)))
        return htmx_redirect(self.request, self.get_success_url())

    def get_error_url(self, obj) -> str:
        return safe_next(self.request, self.get_success_url())
