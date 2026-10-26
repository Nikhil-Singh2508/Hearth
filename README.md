# Hearth Rental Management

Rental management application under active development. Owner login, property/apartment management, tenant invitation and acceptance, tenancy lifecycle, rent and payment ledger, manual late fee assessment, deposits, utilities with meter-based bill calculation, inspections, maintenance, tenant notification preferences, reports and CSV exports are implemented. Opted-in payment receipts can be sent through configured Resend and Meta WhatsApp providers. Supabase PostgreSQL and private Storage are supported through backend configuration. Do not deploy this incomplete product for real tenant or financial data without completing the security checklist and production controls.

## Stack

- Python 3.11, FastAPI, Pydantic Settings, SQLAlchemy 2, Alembic, PostgreSQL 16/Supabase, Supabase Storage, Argon2 dependency
- React 19, Vite, TypeScript, React Router, Tailwind CSS, React Hook Form, Zod

## Local development

Copy `.env.example` to `.env` and replace the local database password with a random value. Never commit `.env`.

### Windows PowerShell

```powershell
Copy-Item .env.example .env
docker compose up -d db
Set-Location backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

In a second terminal:

```powershell
Set-Location frontend
npm install
npm run dev
```

### Windows Command Prompt

```bat
copy .env.example .env
docker compose up -d db
cd backend
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

In a second terminal run `cd frontend`, `npm install`, `npm run dev`.

### macOS/Linux

```sh
cp .env.example .env
docker compose up -d db
cd backend
python3.11 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

In a second terminal run `cd frontend`, `npm install`, `npm run dev`.

Set `DATABASE_URL` to the local Compose credentials from `.env`. API development docs are at `/docs`; liveness and readiness are at `/health/live` and `/health/ready`.

After migrations, create the initial owner interactively from `backend` with `python -m app.bootstrap_owner`. The command prompts for an email and a password of at least 8 characters; it refuses to run after an owner already exists. Sign in and open **Tenants** to create a one-time invitation token, send that token through a secure channel, and have the tenant accept it at `/accept-invitation`. Once accepted, select the tenant, property and apartment to create a tenancy with its rent terms and agreed deposit. Use **Security deposits** to record deposit receipts and, after close-out, refunds or deductions. Entries are idempotent and immutable; the app records them but does not transfer funds. The **Agreements** page accepts PDF files up to 10 MB and serves them only through authorized download routes. Files use `var/private/` by default or a configured private Supabase Storage bucket; see [Supabase setup](docs/supabase-setup.md). The invitation token is only displayed when created and is stored server-side as a hash. The **Rent & payments** page records payments received outside Hearth, provides printable receipts, and allows audited full reversals before the payment credit is allocated. It does not initiate a bank/UPI refund. On this page, owners can configure effective-dated fixed, daily, or percentage late fees and manually assess overdue rent. Fees use only unpaid rent principal, honor configured grace/cap and partial-payment basis, and never accrue on prior fees. `POST /api/auth/login` returns session and CSRF cookies; owner mutations require the CSRF cookie value in `X-CSRF-Token`. Owner ledger routes post monthly rent at `/api/tenancies/{id}/charges/rent/{YYYY-MM-DD}` (date must be the first of the month), record payments with an `Idempotency-Key`, and allocate unapplied credits to charges.

## Checks

Backend: `cd backend; .\.venv\Scripts\python -m pytest; .\.venv\Scripts\ruff check app tests` on Windows, or `python -m pytest && ruff check app tests` on macOS/Linux. Frontend: `cd frontend && npm run typecheck && npm run build`.

## Security and product status

See [security checklist](docs/security-checklist.md), [implementation plan](docs/implementation-plan.md), [database design](docs/database-design.md), [business rules](docs/business-rules.md), and [progress](docs/progress.md). The first-owner bootstrap, cookie authentication, invitation acceptance and management UI, tenancy routes, tenant portal, maintenance requests, rent ledger, property UI, private tenancy PDFs, payment reversals, security deposits, utility bill allocation, property expense tracking, inspections, connected owner dashboard reporting and safe period-bounded CSV exports are implemented. Login rate limiting, broader tenant isolation tests, malware scanning, and production deployment controls remain incomplete. Keep synthetic data only until they are complete.

For step-by-step owner and tenant workflows, see the [user guide](docs/user-guide.md).
