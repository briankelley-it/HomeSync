"""Upload validation for documents.

The browser-supplied filename and Content-Type are not trusted. The file type
is decided by its leading bytes ("magic numbers"), and the extension must agree
with what the bytes say. Only formats that browsers cannot execute as script
are accepted (no HTML, SVG, or Office macros).
"""

from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.template.defaultfilters import filesizeformat

# sniffed type -> (allowed extensions, content type served back to browsers)
ALLOWED_TYPES = {
    "pdf": ({".pdf"}, "application/pdf"),
    "png": ({".png"}, "image/png"),
    "jpeg": ({".jpg", ".jpeg"}, "image/jpeg"),
    "webp": ({".webp"}, "image/webp"),
}
ALLOWED_EXTENSIONS = sorted(ext for exts, _ in ALLOWED_TYPES.values() for ext in exts)


def sniff_file_type(header: bytes) -> str | None:
    if header.startswith(b"%PDF-"):
        return "pdf"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if header.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "webp"
    return None


def validate_document(uploaded_file) -> str:
    """Validate an uploaded file and return the content type to store.

    Raises ``ValidationError`` for oversized, empty, unknown, or mismatched files.
    """
    max_bytes = settings.DOCUMENT_MAX_UPLOAD_BYTES
    if uploaded_file.size > max_bytes:
        raise ValidationError(f"Files must be {filesizeformat(max_bytes)} or smaller.")
    if uploaded_file.size == 0:
        raise ValidationError("The file is empty.")

    extension = Path(uploaded_file.name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValidationError(f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}.")

    uploaded_file.seek(0)
    header = uploaded_file.read(16)
    uploaded_file.seek(0)
    sniffed = sniff_file_type(header)
    if sniffed is None or extension not in ALLOWED_TYPES[sniffed][0]:
        raise ValidationError("The file contents do not match its extension.")
    return ALLOWED_TYPES[sniffed][1]
