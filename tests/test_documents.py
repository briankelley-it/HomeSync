from pathlib import Path

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from apps.documents.models import Document
from apps.documents.validators import validate_document
from apps.households.models import Role

from .factories import BillFactory

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def upload(name, content, content_type="application/pdf"):
    return SimpleUploadedFile(name, content, content_type=content_type)


class TestValidator:
    def test_accepts_real_pdf_and_png(self):
        assert validate_document(upload("a.pdf", PDF)) == "application/pdf"
        assert validate_document(upload("a.PNG", PNG, "image/png")) == "image/png"

    @pytest.mark.parametrize(
        ("name", "content"),
        [
            ("evil.html", b"<script>alert(1)</script>"),
            ("evil.pdf", b"<html><script>alert(1)</script>"),  # lies about type
            ("image.pdf", PNG),  # mismatched extension
            ("drawing.svg", b"<svg onload=alert(1)>"),
            ("empty.pdf", b""),
        ],
    )
    def test_rejects_bad_files(self, name, content):
        with pytest.raises(ValidationError):
            validate_document(upload(name, content, "application/pdf"))

    @override_settings(DOCUMENT_MAX_UPLOAD_BYTES=100)
    def test_rejects_oversized(self):
        with pytest.raises(ValidationError, match="or smaller"):
            validate_document(upload("big.pdf", PDF + b"0" * 200))


class TestUploadAndDownload:
    def _upload(self, client, **extra):
        data = {
            "title": "March invoice",
            "kind": "invoice",
            "file": upload("Invoice March.pdf", PDF),
        }
        data.update(extra)
        return client.post(reverse("documents:upload"), data)

    def test_upload_stores_random_name_and_sniffed_type(self, auth_client, household):
        response = self._upload(auth_client)
        assert response.status_code == 302
        doc = Document.objects.get()
        assert doc.household == household
        assert doc.content_type == "application/pdf"
        assert doc.original_filename == "Invoice March.pdf"
        assert "Invoice" not in doc.file.name
        assert doc.file.name.startswith(f"households/{household.pk}/documents/")

    def test_upload_rejects_disguised_file(self, auth_client):
        response = auth_client.post(
            reverse("documents:upload"),
            {"title": "x", "kind": "other", "file": upload("x.pdf", b"MZ\x90\x00 not a pdf")},
        )
        assert response.status_code == 200
        assert not Document.objects.exists()

    def test_cannot_attach_to_other_household_bill(self, auth_client, other_household):
        foreign_bill = BillFactory(household=other_household)
        self._upload(auth_client, bill=foreign_bill.pk)
        assert not Document.objects.exists()

    def test_download_requires_membership(
        self, auth_client, client_for, household, other_household
    ):
        self._upload(auth_client)
        doc = Document.objects.get()
        response = auth_client.get(reverse("documents:download", args=[doc.pk]))
        assert response.status_code == 200
        assert response["Content-Type"] == "application/pdf"
        assert response["X-Content-Type-Options"] == "nosniff"
        assert "sandbox" in response["Content-Security-Policy"]
        assert b"".join(response.streaming_content) == PDF

        outsider = other_household.memberships.first().user
        response = client_for(outsider).get(reverse("documents:download", args=[doc.pk]))
        assert response.status_code == 404

    def test_download_attachment_mode(self, auth_client):
        self._upload(auth_client)
        doc = Document.objects.get()
        response = auth_client.get(reverse("documents:download", args=[doc.pk]), {"download": "1"})
        assert response["Content-Disposition"].startswith("attachment")

    def test_anonymous_cannot_download(self, auth_client, client):
        self._upload(auth_client)
        doc = Document.objects.get()
        client.logout()
        response = client.get(reverse("documents:download", args=[doc.pk]))
        assert response.status_code == 302

    def test_viewer_cannot_upload(self, client_for, make_member):
        client = client_for(make_member(Role.VIEWER).user)
        assert self._upload(client).status_code == 403

    def test_delete_removes_file(self, auth_client, django_capture_on_commit_callbacks):
        self._upload(auth_client)
        doc = Document.objects.get()
        path = Path(doc.file.path)
        assert path.exists()
        with django_capture_on_commit_callbacks(execute=True):
            auth_client.post(reverse("documents:delete", args=[doc.pk]))
        assert not Document.objects.exists()
        assert not path.exists()
