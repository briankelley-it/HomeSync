from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import CreateView, ListView
from django_ratelimit.decorators import ratelimit

from apps.core.mixins import FormPageMixin, HouseholdDeleteView, htmx_redirect, safe_next
from apps.households.permissions import HouseholdEditMixin, HouseholdFormMixin, HouseholdMixin
from apps.households.services import log_activity

from .forms import DocumentForm
from .models import Document


class DocumentListView(HouseholdMixin, ListView):
    model = Document
    template_name = "documents/document_list.html"
    paginate_by = 30

    def get_queryset(self):
        qs = super().get_queryset().select_related("bill", "property", "uploaded_by")
        if self.request.GET.get("kind") in Document.Kind.values:
            qs = qs.filter(kind=self.request.GET["kind"])
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["kinds"] = Document.Kind.choices
        return context


@method_decorator(
    ratelimit(key="user_or_ip", rate="30/h", method="POST", block=True), name="dispatch"
)
class DocumentUploadView(HouseholdEditMixin, HouseholdFormMixin, FormPageMixin, CreateView):
    model = Document
    form_class = DocumentForm
    page_title = "Upload a document"
    submit_label = "Upload"
    success_url = reverse_lazy("documents:list")

    def get_initial(self):
        initial = super().get_initial()
        for key in ("bill", "property"):
            if self.request.GET.get(key, "").isdigit():
                initial[key] = self.request.GET[key]
        return initial

    def form_valid(self, form):
        form.instance.household = self.household
        form.instance.uploaded_by = self.request.user
        document = form.save()
        log_activity(
            self.household, self.request.user, "uploaded", f"Uploaded document {document.title}"
        )
        messages.success(self.request, f"Uploaded {document.title}.")
        self.object = document
        target = document.bill.get_absolute_url() if document.bill else str(self.success_url)
        return htmx_redirect(self.request, safe_next(self.request, target))


class DocumentDownloadView(HouseholdMixin, View):
    """Stream a document to an authorized household member.

    Files live outside any public URL; this view is the only way to read them.
    PDFs and images open inline in a sandboxed context; ``?download=1`` forces
    a download.
    """

    def get(self, request, pk):
        document = get_object_or_404(Document, pk=pk, household=self.household)
        try:
            handle = document.file.open("rb")
        except FileNotFoundError as exc:
            raise Http404("File is missing.") from exc
        response = FileResponse(
            handle,
            content_type=document.content_type,
            as_attachment=request.GET.get("download") == "1",
            filename=document.original_filename,
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "sandbox; default-src 'none'; img-src 'self'"
        response["Cache-Control"] = "private, no-store"
        return response


class DocumentDeleteView(HouseholdDeleteView):
    model = Document
    object_label = "document"
    success_url = reverse_lazy("documents:list")
