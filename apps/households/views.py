from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import FormView, UpdateView

from . import services
from .forms import HouseholdForm, InvitationForm, RoleForm
from .middleware import SESSION_KEY
from .models import Invitation, Membership
from .permissions import HouseholdManageMixin, HouseholdMixin, require_role


class HouseholdCreateView(LoginRequiredMixin, FormView):
    form_class = HouseholdForm
    template_name = "households/create.html"

    def form_valid(self, form):
        household = services.create_household(user=self.request.user, **form.cleaned_data)
        self.request.session[SESSION_KEY] = household.pk
        messages.success(self.request, f"{household.name} is ready.")
        return redirect("core:dashboard")


@login_required
@require_POST
def switch_household(request):
    membership = get_object_or_404(
        Membership, user=request.user, household_id=request.POST.get("household")
    )
    request.session[SESSION_KEY] = membership.household_id
    return redirect("core:dashboard")


class HouseholdSettingsView(HouseholdManageMixin, UpdateView):
    form_class = HouseholdForm
    template_name = "households/settings.html"
    success_url = reverse_lazy("households:settings")

    def get_object(self, queryset=None):
        return self.household

    def form_valid(self, form):
        messages.success(self.request, "Household settings saved.")
        return super().form_valid(form)


class MembersView(HouseholdMixin, FormView):
    """Member list plus the invitation form (admins only may submit it)."""

    template_name = "households/members.html"
    form_class = InvitationForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["membership"] = self.membership
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["members"] = self.household.memberships.select_related("user").order_by(
            "user__email"
        )
        context["invitations"] = self.household.invitations.pending()
        context["role_form"] = RoleForm()
        return context

    def form_valid(self, form):
        try:
            invitation, raw_token = services.invite_member(
                household=self.household, invited_by=self.membership, **form.cleaned_data
            )
        except ValidationError as exc:
            form.add_error("email", exc.messages[0])
            return self.form_invalid(form)
        accept_url = self.request.build_absolute_uri(
            reverse("households:accept_invitation", args=[raw_token])
        )
        body = render_to_string(
            "households/emails/invitation.txt",
            {"invitation": invitation, "accept_url": accept_url, "inviter": self.request.user},
        )
        transaction.on_commit(
            lambda: send_mail(
                f"You're invited to {self.household.name} on HouseLedger",
                body,
                settings.DEFAULT_FROM_EMAIL,
                [invitation.email],
            )
        )
        messages.success(self.request, f"Invitation sent to {invitation.email}.")
        return redirect("households:members")

    def post(self, request, *args, **kwargs):
        require_role(self.membership, "admin")
        return super().post(request, *args, **kwargs)


@login_required
@require_POST
def change_member_role(request, pk):
    target = get_object_or_404(Membership, pk=pk, household=request.household)
    form = RoleForm(request.POST)
    if form.is_valid():
        try:
            services.change_role(
                actor=request.membership, target=target, role=form.cleaned_data["role"]
            )
            messages.success(request, f"Updated role for {target.user.display_name}.")
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
    return redirect("households:members")


@login_required
@require_POST
def remove_member(request, pk):
    target = get_object_or_404(Membership, pk=pk, household=request.household)
    leaving = target.pk == request.membership.pk
    try:
        services.remove_member(actor=request.membership, target=target)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
        return redirect("households:members")
    if leaving:
        request.session.pop(SESSION_KEY, None)
        messages.success(request, "You left the household.")
        return redirect("core:dashboard")
    messages.success(request, f"Removed {target.user.display_name}.")
    return redirect("households:members")


@login_required
@require_POST
def revoke_invitation(request, pk):
    require_role(request.membership, "admin")
    invitation = get_object_or_404(Invitation, pk=pk, household=request.household)
    invitation.revoked = True
    invitation.save(update_fields=["revoked", "updated_at"])
    messages.success(request, f"Invitation for {invitation.email} revoked.")
    return redirect("households:members")


def accept_invitation(request, token):
    invitation = Invitation.find_pending(token)
    if invitation is None:
        return render(request, "households/invitation_invalid.html", status=404)
    if not request.user.is_authenticated:
        # Remember where to come back to after signing in or registering.
        request.session["pending_invitation_url"] = request.path
        messages.info(request, "Sign in or create an account to accept your invitation.")
        return redirect(f"{reverse('accounts:login')}?next={request.path}")
    if request.method == "POST":
        try:
            membership = services.accept_invitation(invitation=invitation, user=request.user)
        except (ValidationError, PermissionDenied) as exc:
            messages.error(request, getattr(exc, "messages", [str(exc)])[0])
            return redirect("core:dashboard")
        request.session[SESSION_KEY] = membership.household_id
        messages.success(request, f"You joined {membership.household.name}.")
        return redirect("core:dashboard")
    return render(request, "households/accept_invitation.html", {"invitation": invitation})
