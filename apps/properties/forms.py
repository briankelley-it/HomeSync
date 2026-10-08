from django import forms

from apps.core.forms import HouseholdModelForm

from .models import Property


class PropertyForm(HouseholdModelForm):
    household_scoped_fields = ("members",)

    class Meta:
        model = Property
        fields = (
            "name",
            "property_type",
            "address_line1",
            "address_line2",
            "city",
            "state",
            "postal_code",
            "is_primary",
            "members",
            "notes",
        )
        widgets = {
            "members": forms.CheckboxSelectMultiple,
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["members"].queryset = self.fields["members"].queryset.select_related("user")
        self.fields["members"].label_from_instance = lambda m: m.user.display_name
        self.fields["members"].wide = True
        self.fields["address_line1"].wide = True

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        clash = Property.objects.filter(household=self.household, name__iexact=name)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError("You already have a property with this name.")
        return name
