from django.forms.renderers import TemplatesSetting


class AppFormRenderer(TemplatesSetting):
    """Render every form field through ``templates/forms/field.html``."""

    form_template_name = "forms/div.html"
    field_template_name = "forms/field.html"
