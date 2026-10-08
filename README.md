# HouseLedger

**Household bills, recurring payments, budgets, properties, and receipts in one calm dashboard.**

HouseLedger is a full-stack Django application for homeowners, renters, and families. Everyone in a
household can see what is due, record what has been paid, track spending against budgets, and keep
invoices and receipts in one place, across one or several properties.

> HouseLedger never moves money and never stores banking credentials. A bill is only marked paid
> when a household member records a payment.

![Dashboard](docs/screenshots/dashboard.png)

<table>
  <tr>
    <td><img src="docs/screenshots/dashboard-dark.png" alt="Dashboard in dark mode"></td>
    <td><img src="docs/screenshots/calendar.png" alt="Bill calendar"></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/analytics.png" alt="Analytics"></td>
    <td><img src="docs/screenshots/record-payment-dialog.png" alt="Record payment dialog"></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/bill-detail.png" alt="Bill detail with payment history"></td>
    <td><img src="docs/screenshots/budgets.png" alt="Budgets and income in dark mode"></td>
  </tr>
</table>

<p align="center"><img src="docs/screenshots/mobile-dashboard.png" alt="Mobile dashboard" width="280"></p>

---

## Contents

- [Features](#features)
- [Tech stack](#tech-stack)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Architecture](#architecture)
- [Security](#security)
- [Testing](#testing)
- [REST API](#rest-api)
- [Deployment](#deployment)
- [Project layout](#project-layout)
- [Roadmap](#roadmap)

## Features

| Area | What it does |
|------|--------------|
| **Dashboard** | Bills due this month, due in 7 days, overdue, estimated money remaining, 6-month spending trend, category breakdown, upcoming bills, and recent activity. |
| **Bills** | Add, edit, delete, categorize, and search bills. Built-in categories (rent, mortgage, electricity, gas, water, internet, phone, insurance, subscriptions, and more) plus custom categories per household. |
| **Recurring bills** | Weekly, monthly, quarterly, and annual schedules automatically create upcoming bills. Generation is idempotent and never duplicates or resurrects a skipped bill. |
| **Calendar** | Interactive monthly calendar with colour-coded payment status and HTMX month navigation. |
| **Payments** | Record full or partial payments; balances and status are derived from payments only. Filterable history with CSV export. |
| **Properties** | Multiple properties per household, each with its own bills, budgets, expenses, documents, and assigned members. |
| **Budgets & analytics** | Monthly category budgets with progress bars, income sources normalized to a monthly figure, one-off expenses, 12-month trend, and month-over-month comparison. |
| **Notifications** | Daily Celery job emails due-soon and overdue reminders according to each user's preferences. |
| **Households & roles** | Email-based accounts, invitations, and viewer / member / admin / owner roles. Users can belong to several households and switch between them. |
| **Documents** | Upload PDF invoices and receipt images with type sniffing, size limits, and permission-checked downloads. |
| **UI** | Responsive, emerald-accented SaaS design with a left sidebar, dark mode, dialogs, and accessible forms. Every dialog also works as a normal page without JavaScript. |
| **REST API** | Household-scoped JSON API for every resource, built on the same service layer as the web UI. |

## Tech stack

| Layer | Choice |
|-------|--------|
| Backend | Python 3.12, Django 5.2 LTS |
| API | Django REST Framework |
| Database | PostgreSQL 17 |
| Background jobs | Celery 5 with Redis (broker, results, and shared cache) |
| Frontend | Django templates, Tailwind CSS v4, HTMX 2, Chart.js 4 |
| Auth | Django authentication (custom email-based user model) |
| Tests | pytest, pytest-django, factory_boy, Playwright |
| Quality | Ruff (lint + format, including bandit security rules) |
| Packaging | uv (Python), npm (frontend build only) |
| Delivery | Docker, Docker Compose, GitHub Actions, Dependabot |

## Quick start

### Option A: everything in Docker

```bash
cp .env.example .env
# Set DJANGO_SECRET_KEY in .env, for example with:
python -c "import secrets; print(secrets.token_urlsafe(50))"
docker compose up --build
```

Open <http://localhost:8000> to register, and <http://localhost:8025> (Mailpit) to read the emails
the app sends (invitations, password resets, and bill reminders).

Compose starts PostgreSQL, Redis, Mailpit, a one-shot `migrate` job, the gunicorn `web` server, a
Celery `worker`, and Celery `beat`.

### Option B: local development

Prerequisites: [uv](https://docs.astral.sh/uv/), Node.js 22+, and Docker (for PostgreSQL and Redis).

```bash
cp .env.example .env               # then set DJANGO_SECRET_KEY and DJANGO_DEBUG=True
docker compose up -d db redis      # databases only
uv sync                            # Python dependencies into .venv
npm ci && npm run build            # Tailwind CSS + vendored htmx/Chart.js
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

In other terminals, start the background jobs (on Windows add `--pool=solo` to the worker):

```bash
uv run celery -A config worker --loglevel=info
uv run celery -A config beat --loglevel=info
```

While editing templates, `npm run watch:css` rebuilds Tailwind on save.

If port 5432 is already in use on your machine, set `POSTGRES_HOST_PORT=5433` in `.env` and point
`DATABASE_URL` at that port.

### Demo data (development only)

```bash
# Set DEMO_USER_PASSWORD in .env first.
uv run python manage.py seed_demo           # creates demo@houseledger.test
uv run python manage.py seed_demo --reset   # recreate from scratch
```

`seed_demo` refuses to run unless `DJANGO_DEBUG=True`, so sample financial data can never be created
in production. `scripts/screenshots.py` regenerates the README screenshots from that demo data.

## Configuration

All configuration comes from environment variables (or `.env` locally). Nothing secret is committed.

| Variable | Default | Purpose |
|----------|---------|---------|
| `DJANGO_SECRET_KEY` | *(required)* | Cryptographic signing key. |
| `DJANGO_DEBUG` | `False` | Never enable in production. |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated host names. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | *(empty)* | e.g. `https://ledger.example.com` |
| `DATABASE_URL` | *(required)* | `postgres://user:pass@host:5432/db` |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker and result backend. |
| `CACHE_URL` | `locmemcache://` | Use `rediscache://…` in production so rate limits are shared. |
| `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` | console backend | Outgoing email. |
| `DEFAULT_FROM_EMAIL` | `HouseLedger <no-reply@localhost>` | Sender address. |
| `SITE_URL` | `http://localhost:8000` | Absolute links in reminder emails. |
| `TIME_ZONE` | `UTC` | Household "today" and the Celery beat schedule. |
| `MEDIA_ROOT` | `./private_media` | Where uploaded documents are stored (not web-served). |
| `DOCUMENT_MAX_UPLOAD_BYTES` | `10485760` | Upload size limit (10 MB). |
| `RECURRING_BILL_HORIZON_DAYS` | `60` | How far ahead recurring bills are created. |
| `DJANGO_ADMIN_URL` | `admin/` | Move the admin to a less guessable path. |
| `DJANGO_SECURE_SSL_REDIRECT` | `True` (when not DEBUG) | Set `False` only for plain-HTTP local containers. |
| `DJANGO_SECURE_HSTS_SECONDS` / `DJANGO_SECURE_HSTS_PRELOAD` | 30 days / `False` | HSTS policy. |
| `RATELIMIT_ENABLE` | `True` | Rate limiting for sensitive endpoints. |

## Architecture

```mermaid
flowchart LR
    Browser["Browser<br/>Tailwind · HTMX · Chart.js"] -->|HTML + HTMX| Web
    Client["API client"] -->|JSON /api/v1| Web
    subgraph Django["Django (gunicorn)"]
        Web["Views & DRF viewsets"] --> Services["Service layer<br/>(transactions, rules)"]
        Services --> ORM["Models / ORM"]
    end
    ORM --> PG[(PostgreSQL)]
    Web --> Cache[(Redis cache<br/>rate limits)]
    Beat["Celery beat"] -->|daily| Redis[(Redis broker)]
    Redis --> Worker["Celery worker"]
    Worker --> Services
    Worker --> SMTP["SMTP / Mailpit"]
    Web --> Files[("Private media<br/>(documents)")]
```

### Design principles

- **The household is the security boundary.** Every financial row has a `household` foreign key.
  `CurrentHouseholdMiddleware` re-validates the user's membership on every request, view mixins
  filter querysets by household (other households' records return 404), and form/serializer
  dropdowns only offer the household's own properties, categories, and members.
- **Business rules live in `services.py`.** Views, the REST API, and Celery tasks all call the same
  functions, for example `payments.services.record_payment` or `bills.services.generate_bills`.
- **Money is `Decimal`.** All amounts use `DecimalField(max_digits=12, decimal_places=2)`, aggregates
  run in PostgreSQL, and chart/API payloads carry decimal *strings*, never floats.
- **The database enforces invariants too:** positive amounts, valid date ranges, one membership per
  user and household, unique category and property names, and at most one bill per recurring
  occurrence.

### Django apps

| App | Responsibility |
|-----|----------------|
| `accounts` | Email-based `User`, registration, login/logout, password change/reset, profile. |
| `households` | `Household`, `Membership` (roles), hashed-token `Invitation`, `ActivityLog`, active-household middleware, permission mixins. |
| `properties` | `Property` and member assignment. |
| `bills` | `Category`, `RecurringBill`, `Bill`, the recurrence engine, calendar, bill views and API. |
| `payments` | `Payment`, transactional recording and history, CSV export. |
| `budgets` | `Budget`, `IncomeSource`, `Expense`, and the analytics service behind every chart. |
| `notifications` | `NotificationPreference`, `ReminderLog`, reminder selection and Celery tasks. |
| `documents` | `Document` uploads, validation, and protected downloads. |
| `core` | Shared base model, `MoneyField`, view mixins, template tags, dashboard, health check. |

### Data model

```mermaid
erDiagram
    User ||--o{ Membership : has
    Household ||--o{ Membership : has
    Household ||--o{ Property : owns
    Household ||--o{ Bill : owes
    Household ||--o{ RecurringBill : schedules
    Household ||--o{ Expense : records
    Household ||--o{ Budget : plans
    Household ||--o{ IncomeSource : earns
    Household ||--o{ Document : stores
    Property }o--o{ Membership : "assigned members"
    RecurringBill ||--o{ Bill : generates
    Category ||--o{ Bill : classifies
    Bill ||--o{ Payment : "paid by"
    Bill ||--o{ Document : "attached to"
    Bill ||--o{ ReminderLog : reminded
```

### How key workflows stay correct

**Recording a payment.** `record_payment` runs in `transaction.atomic()` and locks the bill row
with `SELECT … FOR UPDATE`. It rejects non-positive, future-dated, or overpaying amounts, then
recalculates `amount_paid`, `status` (unpaid / partial / paid), and `paid_on` from the payment
rows. A test runs two threads paying the same bill concurrently and asserts that exactly one
succeeds.

**Recurring bills.** Each schedule records `generated_through`. The daily job only creates
occurrences after that date, so a bill the user deleted (for example, a skipped month) is not
recreated. A partial unique index on `(recurring_id, due_date)` guards against duplicates even
if two workers run at once. Occurrences are computed as `start + n × interval`, so a bill due
on the 31st falls on the last day of shorter months and returns to the 31st afterwards. Editing a
schedule replaces only its future bills that have no payments; paid history is never touched.

**Reminders.** One digest email per user and household lists due-soon and overdue bills. If a
bill's property has assigned members, only they are reminded. `ReminderLog` (unique on bill, user,
and kind) makes each reminder send once; if sending fails, the log rows roll back so the reminder
is retried on the next run.

**Deleting.** Bills with payments cannot be deleted (`on_delete=RESTRICT` plus a service check),
which protects payment history. Deleting an entire household (owner only, with name confirmation)
still cascades cleanly, because `RESTRICT` allows deletions that are part of the same cascade.

## Security

| Concern | Measure |
|---------|---------|
| Authorization | Server-side household scoping on every view and API endpoint; role checks for writes; 404 (not 403) for other households' objects. |
| CSRF | Django CSRF middleware; HTMX sends the token through `hx-headers`; DRF session auth enforces CSRF. |
| Sessions & cookies | `HttpOnly`, `SameSite=Lax`; `Secure` cookies, SSL redirect, HSTS, and proxy SSL header when `DEBUG=False`. |
| Brute force | `django-ratelimit` on login (per IP and per email), registration, password reset/change, and uploads; DRF throttling on the API; Redis cache so limits are shared. |
| Passwords | Django's PBKDF2 hashing, minimum length 10, common/numeric/similarity validators; reset links expire after 2 hours. |
| Invitations | Tokens are random 256-bit values and only their SHA-256 hash is stored; expire after 7 days; must be accepted by the invited email address. |
| Uploads | Extension allow-list (PDF, PNG, JPEG, WebP) **and** magic-byte sniffing must agree; 10 MB limit; random storage names; stored outside the web root; streamed only through a permission-checked view with `nosniff`, `Content-Security-Policy: sandbox`, and `Cache-Control: private, no-store`. |
| Redirects | `?next=` parameters are validated with `url_has_allowed_host_and_scheme` (no open redirects or `javascript:` links). |
| Exports | CSV export neutralizes spreadsheet formula injection. |
| Headers | `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`, `X-Content-Type-Options: nosniff`. |
| Secrets | Environment variables only; `.env` is git-ignored; demo data is gated behind `DEBUG`. |
| Supply chain | CI runs `pip-audit` and `npm audit` on shipped packages; Dependabot keeps uv, npm, Actions, and Docker images current; Ruff's bandit rules run on every push. |
| Containers | The app runs as an unprivileged user; only the uploads directory is writable. |

## Testing

```bash
uv run pytest                     # unit + integration tests (PostgreSQL), 220 tests
uv run pytest --cov               # with coverage (fails under 85%; currently ~94%)
uv run playwright install chromium
uv run pytest -m e2e              # Playwright browser tests (needs `npm run build`)
uv run ruff check . && uv run ruff format --check .
```

| Suite | Covers |
|-------|--------|
| `test_accounts.py` | User model, registration, login/logout, rate limiting, password reset. |
| `test_households.py` | Roles, invitations (hashing, expiry, wrong email), switching households, isolation. |
| `test_bill_models.py` | Constraints, status logic, categories, cross-household form tampering. |
| `test_payments.py` | Full/partial/over-payments, deletes, status recalculation, **concurrent payment race**. |
| `test_recurring.py` | Date math (month-end, leap years), idempotency, skips, horizon, schedule edits. |
| `test_views.py` | Every page renders for viewers, login required, HTMX dialogs, permissions, 404 isolation, open-redirect protection. |
| `test_analytics.py` | Income normalization, trends, category breakdowns, budgets, dashboard summary. |
| `test_documents.py` | File validation (disguised and oversized files), storage names, download authorization, file cleanup. |
| `test_notifications.py` | Reminder rules, preferences, property targeting, dedupe, retry after failure, Celery tasks. |
| `test_api.py` | API isolation, roles, decimal serialization, payments via API, validation. |
| `e2e/test_browser.py` | Real Chromium: onboarding, bill and payment dialogs, calendar, filters, dark mode, mobile nav. |

## REST API

Session-authenticated JSON API under `/api/v1/` (browsable in development). Amounts are decimal
strings. Writes require the CSRF token, as for any Django form.

| Endpoint | Methods | Notes |
|----------|---------|-------|
| `/api/v1/households/` | GET | Households you belong to, with your role. |
| `/api/v1/households/{id}/summary/` | GET | Dashboard figures for the current month. |
| `/api/v1/households/{id}/bills/` | GET, POST | Filters: `status`, `due_after`, `due_before`, `category`, `property`, `search`. |
| `/api/v1/households/{id}/bills/{bill_id}/` | GET, PUT, PATCH, DELETE | `status`, `amount_paid`, `paid_on` are read-only. |
| `/api/v1/households/{id}/bills/{bill_id}/payments/` | GET, POST | Record a full or partial payment. |
| `/api/v1/households/{id}/payments/` | GET, DELETE | History; filters `paid_after`, `paid_before`, `bill`. |
| `/api/v1/households/{id}/recurring-bills/` | CRUD | Creating or editing a schedule generates bills. |
| `/api/v1/households/{id}/categories/` | CRUD | Built-ins are read-only. Writes require admin. |
| `/api/v1/households/{id}/properties/` | CRUD | Writes require admin. |
| `/api/v1/households/{id}/budgets/` | CRUD | Writes require admin. |
| `/api/v1/households/{id}/income-sources/` | CRUD | Writes require admin. |
| `/api/v1/households/{id}/expenses/` | CRUD | |

```http
POST /api/v1/households/1/bills/42/payments/
{"amount": "40.00", "paid_on": "2026-10-08", "method": "card", "reference": "CONF-1234"}

201 Created
{"id": 7, "bill": 42, "amount": "40.00", "paid_on": "2026-10-08", "method": "card", ...}
```

## Deployment

The Docker image is production-ready: gunicorn, WhiteNoise for hashed and compressed static
files, a `/health/` endpoint, and a non-root user. A typical deployment:

1. **Provision** managed PostgreSQL and Redis, plus an SMTP provider (Postmark, SES, SendGrid, …).
2. **Build** the image (`docker build -t houseledger .`) and push it to your registry.
3. **Configure** environment variables: a long random `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`,
   `DJANGO_CSRF_TRUSTED_ORIGINS`, `DATABASE_URL`, `REDIS_URL`, `CACHE_URL=rediscache://…`,
   email settings, `SITE_URL`, and `TIME_ZONE`. Keep `DJANGO_DEBUG=False`.
4. **Run migrations** as a release step: `python manage.py migrate --noinput`.
5. **Run three processes** from the same image: `web` (default command), `worker`
   (`celery -A config worker`), and exactly **one** `beat` (`celery -A config beat`).
6. **Terminate TLS** at your load balancer or reverse proxy and forward `X-Forwarded-Proto`.
   HSTS and secure cookies turn on automatically when `DEBUG=False`.
7. **Persist uploads** by mounting a volume at `MEDIA_ROOT` and backing it up together with the
   database. For multiple web servers, switch the default storage to S3-compatible object storage
   (for example with `django-storages`) and keep the bucket private.
8. **Verify** with `python manage.py check --deploy` and the `/health/` endpoint.

## Project layout

```
config/                 settings (base, test), URLs, API routes, Celery app, WSGI/ASGI
apps/
  accounts/ households/ properties/ bills/ payments/
  budgets/ notifications/ documents/ core/
templates/              layouts, partials (HTMX fragments), and per-app pages
assets/css/input.css    Tailwind v4 design tokens and components
static/                 app.js, charts.js, favicon (built CSS and vendor JS are generated)
tests/                  pytest suites and tests/e2e Playwright tests
scripts/                vendor.mjs (frontend build), screenshots.py
docs/                   implementation plan and screenshots
Dockerfile, docker-compose.yml, .github/workflows/ci.yml
```

## Roadmap

- Token or OAuth authentication for third-party API clients.
- Bank statement CSV import with manual matching. Imported rows will still need a user's
  confirmation before a bill counts as paid.
- Shared-expense splitting between household members.
- S3-compatible document storage with signed, short-lived download URLs.
- Multi-currency households with explicit conversion rates.
