"""Celery application. Tasks are discovered from each app's ``tasks.py``."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.base")

app = Celery("houseledger")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
