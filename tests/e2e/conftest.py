"""Playwright fixtures. Run with: uv run pytest -m e2e

Requires built frontend assets (``npm run build``) and a Chromium install
(``uv run playwright install chromium``).
"""

import os

import pytest

# Playwright's sync API runs an event loop in the test thread; Django's ORM
# refuses to run there unless told it is safe (it is: tests are sequential).
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


@pytest.fixture(autouse=True)
def builtin_categories(transactional_db):
    """Live-server tests truncate tables between tests; restore seeded categories."""
    from importlib import import_module

    from apps.bills.models import Category

    seed = import_module("apps.bills.migrations.0003_seed_default_categories")
    for name, color in seed.DEFAULT_CATEGORIES:
        Category.objects.get_or_create(household=None, name=name, defaults={"color": color})


@pytest.fixture
def login(page, live_server, password):
    def _login(user):
        page.goto(f"{live_server.url}/accounts/login/")
        page.get_by_label("Email").fill(user.email)
        page.get_by_label("Password").fill(password)
        page.get_by_role("button", name="Sign in").click()
        page.wait_for_url(f"{live_server.url}/")
        return page

    return _login
