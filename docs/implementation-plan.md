# Implementation plan

This repository starts empty. The target is a secure modular monolith: FastAPI, SQLAlchemy 2, Alembic and PostgreSQL behind a React/Vite TypeScript application.

## Delivery phases

1. **Foundation:** repository layout, pinned dependencies, environment configuration, Docker Compose, database connectivity, health endpoints, initial migration, and developer commands.
2. **Identity and audit:** Argon2 password hashing, invitation-only tenant onboarding, secure bootstrap, role checks, session lifecycle, and append-only audit records.
3. **Portfolio:** properties, units, tenant profiles, tenancy periods, effective-dated rent terms, and private document metadata/storage.
4. **Ledger:** monthly charges and proration snapshots, fees, manual payments, allocation and credits, reversals, and receipts.
5. **Deposits:** transactions, deductions, evidence, disputes, settlement and refund history.
6. **Utilities and expenses:** meters, readings, rates, bills, reconciled allocations, and expenses.
7. **Operations:** inspections, private media, maintenance, tenant portal, notifications, and consent controls.
8. **Reporting and release:** dashboards, safe CSV export, responsive/accessibility polish, regression/security checks, backup/restore and deployment documentation.

## Architecture decisions

- Keep one deployable backend with domain services and explicit authorization dependencies.
- Use PostgreSQL UUID keys, `NUMERIC(12,2)` INR amounts, UTC timestamps, transactions, unique idempotency keys, and migrations.
- Use server-side sessions in secure HttpOnly cookies with CSRF protection for browser mutations; never place bearer credentials in local storage.
- Bootstrap the first owner only via a CLI command that requires an explicit email and password supplied interactively or through a secret environment variable.
- Keep uploaded files private, store opaque names and metadata in the database, and authorize each retrieval.
- Default optional outbound communication providers to disabled.

## Verification policy

Each phase should have meaningful unit/API tests and should run the applicable formatter, linter, type checker, test suite, migration check and frontend production build. Never use production data in tests. This first delivery will prioritize a sound runnable foundation and a tested vertical slice; unfinished modules and unavailable local services must be listed in `progress.md` rather than represented as complete.
