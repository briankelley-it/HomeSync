from apps.core.forms import HouseholdModelForm

from .models import Document
from .validators import ALLOWED_EXTENSIONS, validate_document


class DocumentForm(HouseholdModelForm):
    household_scoped_fields = ("bill", "property")

    class Meta:
        model = Document
        fields = ("title", "kind", "file", "bill", "property")
        labels = {"bill": "Related bill", "property": "Property"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["file"].widget.attrs["accept"] = ",".join(ALLOWED_EXTENSIONS)
        self.fields["file"].help_text = "PDF, PNG, JPG, or WEBP."
        self.fields["bill"].queryset = self.fields["bill"].queryset.order_by("-due_date")

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        self.detected_content_type = validate_document(uploaded)
        return uploaded

    def save(self, commit=True):
        document = super().save(commit=False)
        uploaded = self.cleaned_data["file"]
        document.original_filename = uploaded.name[:255]
        document.content_type = self.detected_content_type
        document.size = uploaded.size
        if commit:
            document.save()
        return document
