from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Document


@receiver(post_delete, sender=Document)
def delete_file_with_document(sender, instance: Document, **kwargs) -> None:
    """Remove the stored file once the row is gone (also covers cascades).

    Deferred to on_commit so a rolled-back delete never loses the file.
    """
    if instance.file:
        storage, name = instance.file.storage, instance.file.name
        transaction.on_commit(lambda: storage.delete(name))
