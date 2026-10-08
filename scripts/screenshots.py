"""Capture README screenshots from a running dev server seeded with `seed_demo`.

Usage:
    uv run python manage.py seed_demo --reset
    uv run python manage.py runserver
    uv run python scripts/screenshots.py   # reads DEMO_USER_PASSWORD from .env
"""

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
BASE = os.environ.get("BASE_URL", "http://localhost:8000")
EMAIL = "demo@houseledger.test"


def demo_password() -> str:
    if value := os.environ.get("DEMO_USER_PASSWORD"):
        return value
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("DEMO_USER_PASSWORD="):
            return line.split("=", 1)[1].strip()
    sys.exit("DEMO_USER_PASSWORD is not set")


PAGES = [
    ("dashboard", "/", "light"),
    ("dashboard-dark", "/", "dark"),
    ("bills", "/bills/", "light"),
    ("calendar", "/bills/calendar/", "light"),
    ("analytics", "/budgets/analytics/", "light"),
    ("budgets", "/budgets/", "dark"),
    ("properties", "/properties/", "light"),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1440, "height": 900}, device_scale_factor=1
        )
        page = context.new_page()
        page.goto(f"{BASE}/accounts/login/")
        page.screenshot(path=OUT / "login.png")
        page.fill("input[name=username]", EMAIL)
        page.fill("input[name=password]", demo_password())
        page.click("button[type=submit]")
        page.wait_for_url(f"{BASE}/")

        for name, path, theme in PAGES:
            page.evaluate(f"localStorage.setItem('theme', '{theme}')")
            page.goto(f"{BASE}{path}")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(600)  # let Chart.js finish its animation
            page.screenshot(path=OUT / f"{name}.png", full_page=name != "calendar")
            print(f"saved {name}.png")

        page.evaluate("localStorage.setItem('theme', 'light')")
        page.goto(f"{BASE}/bills/")
        page.get_by_role("link", name="Record payment").first.click()
        page.locator("#modal[open] input[name=amount]").wait_for()
        page.screenshot(path=OUT / "record-payment-dialog.png")
        page.keyboard.press("Escape")
        bill = page.locator("table a[href^='/bills/']").first.get_attribute("href")
        page.goto(f"{BASE}{bill}")
        page.screenshot(path=OUT / "bill-detail.png", full_page=True)

        mobile = browser.new_context(
            viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True
        )
        mobile.add_cookies(context.cookies())
        mpage = mobile.new_page()
        mpage.goto(f"{BASE}/")
        mpage.wait_for_load_state("networkidle")
        mpage.wait_for_timeout(600)
        mpage.screenshot(path=OUT / "mobile-dashboard.png")
        browser.close()


if __name__ == "__main__":
    main()
