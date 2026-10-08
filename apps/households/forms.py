from django import forms

from .models import ROLE_RANK, Household, Role


class HouseholdForm(forms.ModelForm):
    class Meta:
        model = Household
        fields = ("name", "currency")
        labels = {"name": "Household name"}


class InvitationForm(forms.Form):
    email = forms.EmailField()
    role = forms.ChoiceField(choices=Role.choices, initial=Role.MEMBER)

    def __init__(self, *args, membership=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Only offer roles up to the inviter's own role.
        if membership is not None:
            self.fields["role"].choices = [
                (value, label)
                for value, label in Role.choices
                if ROLE_RANK[Role(value)] <= membership.rank
            ]


class RoleForm(forms.Form):
    role = forms.ChoiceField(choices=Role.choices)
