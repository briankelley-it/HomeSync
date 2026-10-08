"""End-to-end browser tests: real Chromium against Django's live server."""

import re
from datetime import timedelta
from decimal import Decimal

import pytest
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from playwright.sync_api import expect

from apps.bills.models import Bill

from ..factories import BillFactory, HouseholdFactory, MembershipFactory

pytestmark = pytest.mark.e2e
TODAY = timezone.localdate()


def test_register_and_create_household(page, live_server):
    page.goto(f"{live_server.url}/accounts/register/")
    page.get_by_label("First name").fill("Riley")
    page.get_by_label("Email").fill("riley@example.com")
    page.get_by_label("Password", exact=True).fill("a-long-and-unique-passphrase")
    page.get_by_label("Password confirmation").fill("a-long-and-unique-passphrase")
    page.get_by_role("button", name="Create account").click()

    expect(page).to_have_url(re.compile(r"/households/new/$"))
    page.get_by_label("Household name").fill("Riley's Place")
    page.get_by_role("button", name="Create household").click()

    expect(page.get_by_role("heading", name="Good to see you, Riley")).to_be_visible()
    expect(page.get_by_text("Let's set up Riley's Place")).to_be_visible()


def test_add_bill_and_record_payments_in_dialogs(page, live_server, login, owner):
    login(owner.user)
    page.goto(f"{live_server.url}/bills/")

    page.get_by_role("link", name="Add bill").click()
    dialog = page.locator("dialog#modal")
    expect(dialog).to_be_visible()
    dialog.get_by_label("Name").fill("Electric company")
    dialog.get_by_label("Category").select_option(label="Electricity")
    dialog.get_by_label("Amount due").fill("120.00")
    dialog.get_by_label("Due date").fill((TODAY + timedelta(days=3)).isoformat())
    dialog.get_by_role("button", name="Save bill").click()

    expect(page.get_by_role("heading", name="Electric company")).to_be_visible()
    expect(page.get_by_text("Due soon").first).to_be_visible()

    # Partial payment from the bills list dialog.
    page.goto(f"{live_server.url}/bills/")
    page.get_by_role("link", name="Record payment").click()
    expect(dialog).to_be_visible()
    dialog.get_by_label("Amount").fill("20.00")
    dialog.get_by_role("button", name="Record payment").click()
    expect(page.get_by_text("Partially paid").first).to_be_visible()
    expect(page.get_by_text("$100.00").first).to_be_visible()

    # Pay the rest from the bill page form.
    page.get_by_role("button", name="Record payment").click()
    expect(page.get_by_text("Paid in full")).to_be_visible()
    bill = Bill.objects.get(name="Electric company")
    assert bill.status == "paid" and bill.amount_paid == Decimal("120.00")


def test_dialog_shows_validation_errors(page, live_server, login, owner):
    login(owner.user)
    page.goto(f"{live_server.url}/bills/")
    page.get_by_role("link", name="Add bill").click()
    page.locator("dialog#modal").get_by_role("button", name="Save bill").click()
    expect(
        page.locator("dialog#modal").get_by_text("This field is required.").first
    ).to_be_visible()


def test_calendar_navigates_with_htmx(page, live_server, login, owner, household):
    next_month = TODAY.replace(day=1) + relativedelta(months=1)
    BillFactory(household=household, name="Next month rent", due_date=next_month.replace(day=5))
    login(owner.user)
    page.goto(f"{live_server.url}/bills/calendar/")
    heading = page.get_by_test_id("calendar-month")
    expect(heading).to_have_text(TODAY.strftime("%B %Y"))

    page.get_by_role("link", name="Next month").click()
    expect(heading).to_have_text(next_month.strftime("%B %Y"))
    expect(page.get_by_text("Next month rent")).to_be_visible()
    expect(page).to_have_url(re.compile(rf"month={next_month.month}"))


def test_bill_filters_update_table(page, live_server, login, owner, household):
    BillFactory(household=household, name="Late fee", due_date=TODAY - timedelta(days=2))
    BillFactory(household=household, name="Streaming", due_date=TODAY + timedelta(days=20))
    login(owner.user)
    page.goto(f"{live_server.url}/bills/")
    page.locator("label").filter(has_text="Overdue").click()
    table = page.locator("#bill-table")
    expect(table.get_by_text("Late fee")).to_be_visible()
    expect(table.get_by_text("Streaming")).to_have_count(0)


def test_dark_mode_persists(page, live_server, login, owner):
    login(owner.user)
    html = page.locator("html")
    expect(html).not_to_have_class(re.compile("dark"))
    page.get_by_role("button", name="Toggle dark mode").click()
    expect(html).to_have_class(re.compile("dark"))
    page.reload()
    expect(html).to_have_class(re.compile("dark"))


def test_mobile_sidebar(page, live_server, login, owner):
    page.set_viewport_size({"width": 390, "height": 844})
    login(owner.user)
    nav_link = page.get_by_role("navigation", name="Main").get_by_role("link", name="Calendar")
    expect(nav_link).not_to_be_in_viewport()
    page.get_by_role("button", name="Open navigation").click()
    expect(nav_link).to_be_in_viewport()
    nav_link.click()
    expect(page).to_have_url(re.compile(r"/bills/calendar/$"))


def test_cannot_open_other_households_bill(page, live_server, login, owner):
    stranger_bill = BillFactory(household=HouseholdFactory(), name="Private")
    MembershipFactory(household=stranger_bill.household)
    login(owner.user)
    response = page.goto(f"{live_server.url}/bills/{stranger_bill.pk}/")
    assert response.status == 404
    expect(page.get_by_text("Private")).to_have_count(0)
