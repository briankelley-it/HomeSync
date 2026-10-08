from django import forms
from django.forms.renderers import TemplatesSetting


class AppFormRenderer(TemplatesSetting):
    """Render every form field through ``templates/forms/field.html``."""

    form_template_name = "forms/div.html"
    field_template_name = "forms/field.html"


class HouseholdModelForm(forms.ModelForm):
    """ModelForm that receives the active household.

    Subclasses list FK/M2M fields in ``household_scoped_fields``; their
    querysets are restricted to the household so a crafted POST cannot attach
    another household's records.
    """

    household_scoped_fields: tuple[str, ...] = ()

    def __init__(self, *args, household, **kwargs):
        self.household = household
        super().__init__(*args, **kwargs)
        for name in self.household_scoped_fields:
            if name in self.fields:
                field = self.fields[name]
                field.queryset = field.queryset.filter(household=household)

    def _post_clean(self):
        # Ensure model-level validation (e.g. unique constraints) sees the household.
        if self.instance.household_id is None:
            self.instance.household = self.household
        super()._post_clean()


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, **kwargs):
        kwargs.setdefault("format", "%Y-%m-%d")
        super().__init__(**kwargs)
