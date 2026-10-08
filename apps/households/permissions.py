"""View mixins and helpers enforcing household-scoped authorization."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from .models import Role


class HouseholdMixin(LoginRequiredMixin):
    """Require login, an active household, and at least ``required_role``.

    Subclasses that set ``model`` get a queryset automatically limited to the
    active household, so objects from other households return 404.
    """

    required_role = Role.VIEWER

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.membership is None:
            return redirect("households:create")
        if not request.membership.has_role(self.required_role):
            raise PermissionDenied("Your household role does not allow this action.")
        self.household = request.household
        self.membership = request.membership
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return super().get_queryset().filter(household=self.household)


class HouseholdEditMixin(HouseholdMixin):
    required_role = Role.MEMBER


class HouseholdManageMixin(HouseholdMixin):
    required_role = Role.ADMIN


class HouseholdFormMixin:
    """Pass the active household into forms and stamp it on new objects."""

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["household"] = self.household
        return kwargs

    def form_valid(self, form):
        if not form.instance.pk:
            form.instance.household = self.household
        return super().form_valid(form)


def require_role(membership, role: str) -> None:
    if membership is None or not membership.has_role(role):
        raise PermissionDenied
