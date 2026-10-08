# HouseLedger — Implementation Plan

HouseLedger is a Django web application for households to track bills, recurring
payments, budgets, properties, receipts, and payment history from one dashboard.

## Guiding principles

- **Household is the security boundary.** Every financial record carries a
  `household` foreign key, and every view/API query is filtered by the requesting
  user's membership. Authorization is enforced server-side, never in templates.
- **Money is `Decimal`.** All amounts are `DecimalField(max_digits=12, decimal_places=2)`.
  No floats anywhere in the money path.
- **Nothing is "paid" unless a user records it.** Bill status is derived only
  from `Payment` rows that a household member entered. No real-money transfers.
- **Business logic lives in `services.py`**, not views. Views and API viewsets
  call the same services, so the web UI and API stay consistent.
- **Configuration comes from the environment** (`.env` locally, real env vars in
  production). No secrets in Git.

## Project layout

```
config/                 Django project: settings/, urls, celery, wsgi/asgi
apps/
  core/                 Shared base models, mixins, dashboard + calendar views
  accounts/             Custom User (email login), registration, profile
  households/           Household, Membership (roles), Invitation, ActivityLog,
                        "current household" middleware, permission helpers
  properties/           Property, property member assignment
  bills/                Category, RecurringBill (schedule), Bill, recurrence engine
  payments/             Payment (full/partial), balance + status recalculation
  budgets/              Budget, IncomeSource, Expense, analytics service
  notifications/        NotificationPreference, ReminderLog, Celery tasks
  documents/            Document uploads with validation + protected download
templates/              Django templates (base layout, sidebar, partials for HTMX)
assets/                 Tailwind source CSS + small JS (theme toggle, charts)
static/                 Built CSS + vendored htmx / Chart.js (generated)
tests/                  pytest unit/integration tests; tests/e2e for Playwright
```

## Roles and permissions

| Role   | Read | Create/edit bills, payments, expenses, documents | Manage properties, budgets, categories | Manage members | Delete household |
|--------|------|------|------|------|------|
| viewer | ✔ |   |   |   |   |
| member | ✔ | ✔ |   |   |   |
| admin  | ✔ | ✔ | ✔ | ✔ |   |
| owner  | ✔ | ✔ | ✔ | ✔ | ✔ |

## Phases

1. **Foundation** — pyproject (uv), settings split, PostgreSQL via `DATABASE_URL`,
   Ruff, pytest config, `.env.example`, `.gitignore`.
2. **Accounts & households** — custom user, registration/login/logout/password
   reset (rate limited), households, memberships, invitations, active-household
   middleware, permission mixins, activity log.
3. **Properties & bills** — categories (seeded defaults + custom), properties,
   bills, recurring schedules.
4. **Bill tracking & payments** — record full/partial payments inside
   `transaction.atomic()` with row locks, overpayment prevention, history views.
5. **Frontend** — base layout with sidebar, dark mode, dashboard metric cards,
   Chart.js trends, bill/payment CRUD with HTMX, monthly calendar, budgets &
   analytics, documents.
6. **Recurring billing & notifications** — idempotent bill generation (DB unique
   constraint on `(recurring_bill, due_date)`), Celery beat jobs, reminder emails
   with per-user preferences and a dedupe log.
7. **REST API** — DRF viewsets scoped to `/api/v1/households/<id>/...`.
8. **Tests** — unit (services, models), integration (views, permissions, API),
   browser (Playwright).
9. **Docker & CI** — multi-stage Dockerfile, Compose (web, worker, beat,
   postgres, redis), GitHub Actions (Ruff, pytest on Postgres, Playwright,
   pip-audit, npm audit), Dependabot.
10. **README** — setup, architecture, testing, deployment.

## Out of scope for v1

- Real bank connections or money movement.
- Storing banking credentials of any kind.
- Multi-currency conversion (each household picks one display currency).
