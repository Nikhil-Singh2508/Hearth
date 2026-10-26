# Hearth Rental Management — User Guide

This guide describes the features currently available in the web application and its authenticated API. The project is still under development; use synthetic data until release checks and production controls are complete.

## 1. Start the application

The local setup uses PostgreSQL in Docker, a FastAPI backend, and a Vite frontend. From the project root, create .env from .env.example if this is your first setup, then make sure it contains the same database credentials used by docker-compose.yml and DATABASE_URL. In this project the Docker database is published on host port 5433.

If you need to create the local runtimes, run:

~~~powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Set-Location frontend
npm install
Set-Location ..
~~~

Start the database:

~~~powershell
docker compose up -d db
~~~

From a PowerShell terminal in backend, activate or use your Python environment, apply migrations, then start the API. If you created the virtual environment at the project root, use ..\.venv; if you created one inside backend, use .venv instead.

~~~powershell
# From the repository root, if using the root .venv:
Set-Location backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
~~~

In a second terminal, start the frontend:

~~~powershell
Set-Location frontend
npm install
npm run dev
~~~

Open http://localhost:5173. The API is at http://localhost:8000; its interactive development reference is http://localhost:8000/docs. Health checks are /health/live and /health/ready.

### First owner account

After the database is running and migrations are applied, create the first owner once:

~~~powershell
# From the repository root, using the root .venv
Set-Location backend
..\.venv\Scripts\python.exe -m app.bootstrap_owner
~~~

The command asks for an email and password (at least 8 characters). It refuses to create another owner if one already exists. Keep this login private. Owners sign in at the frontend URL.

## 2. Owner workflows

### Overview dashboard

The dashboard shows persisted portfolio and financial information, including occupied units, rent charged, payments received, overdue rent, expenses, deposit totals, pending utilities, move-outs, maintenance and inspections. Use the period selector for this month, last month or this quarter. Figures are based on records that have been entered and posted; missing records are not estimated.

### Properties and apartments

1. Open Properties and choose Add property.
2. Enter its name, address and IANA timezone (for example, Asia/Kolkata).
3. Add apartment identifiers inside the property card.
4. Use Edit to update details or Archive to hide a property from the active list.

An apartment number must be unique within its property. Archived properties are not deleted from historical financial records.

### Invite tenants and create tenancies

1. Open Tenants and invite the tenant using their email address.
2. Copy the one-time invitation token and send it to the tenant through a secure channel. The token is shown once and expires after seven days. You can revoke a pending invitation.
3. The tenant opens the invitation link shown in the page, enters the token, display name and password, then accepts the invitation.
4. Return to Tenants and select the accepted tenant, property and apartment.
5. Enter start date, monthly rent, agreed security deposit, due day and proration method. The app records the initial effective rent term.

Overlapping occupancy for one apartment is rejected by the database. Tenancy creation currently happens in the owner page; closing a tenancy is available through the API (see section 4).

### Agreements and tenancy documents

Open Agreements & documents, select a tenancy, and upload a PDF up to 10 MB. The tenant on that tenancy can see and download the document from their portal. Files use a private local directory by default or a private Supabase Storage bucket when configured; downloads remain behind application authorization and are not public links.

### Rent, payment records and receipts

Open Rent & payments to record a payment received outside the app:

1. Select the active tenancy.
2. Enter the amount in INR, payment method, date and optional reference.
3. Choose Record payment. The app records the money as a tenant credit and creates a receipt; it does not contact a bank, UPI provider or payment gateway.
4. Recent payments appear below. Use Receipt to open/print the receipt.
5. Use Reverse only to correct an unapplied payment, and enter a reason. A payment with any amount already allocated cannot be reversed through this action.

Monthly rent charges are not generated automatically by the current UI. Use the API endpoint in section 4 to post rent for a month. Allocating recorded tenant credits to charges is also currently API-only. The payment record returns a credit_id; the rent posting call returns a charge id. Preserve those IDs to allocate credits. Allocation cannot exceed the available credit or the charge balance.

### Late fees

In the lower section of Rent & payments:

1. Select a tenancy and enable late fees.
2. Choose a one-time fixed fee, daily fee or percentage fee; enter the amount, grace days and optional cap.
3. Choose whether partial payments reduce the basis (remaining rent balance) or fees use the original rent amount.
4. Save the rule. It applies from the current date and is effective-dated.
5. For an overdue rent charge, choose Assess today. Daily rules catch up through the assessment date. Repeat assessments on the same date do not duplicate fees.

Fees are based on rent principal only and never accrue on previously assessed fees. Assessment is manual. If a rule is changed after it has been used, create a later effective rule rather than editing its history.

### Security deposits

Open Security deposits, select a tenancy and review the agreed amount, receipts, refunds, deductions and remaining balance.

- Update the agreed amount only when the tenancy is active; it cannot be lower than receipts already recorded.
- Record a receipt while active, up to the remaining agreed amount.
- After closing a tenancy, record a refund or a deduction. Both require a reason; the transaction cannot exceed the remaining deposit balance.

Deposit records are append-only accounting entries. They do not move money to or from a bank.

### Utility bills, meters and property expenses

Open Utilities & expenses.

Manual utility bill: enter the property/apartment, utility, supplier, period, due date, amount and optional reference/notes. The bill remains pending until allocated.

Meter-based billing:

1. Select the property and optional apartment in the bill form's property/apartment selector; the meter and rate forms use that selected scope.
2. Add a meter with its utility type, name, serial number and reading unit (such as kWh or m³).
3. Set the rate per unit and optional fixed charge, plus its effective date. A more specific apartment rate takes precedence over a property-wide rate.
4. Record the first reading as a baseline. Record later readings in date order. The app calculates consumption and creates a pending bill using the rate effective on the reading date.

Reconcile/post bill: select a pending bill, assign its full amount to eligible tenancies, and choose Reconcile and post. Allocations must sum exactly to the bill, match its property/apartment scope and overlap its billing period. Only then are tenant utility charges created. Property expenses are tracked separately and are never automatically charged to tenants.

Property expenses: record the property/apartment, category, date, vendor, amount and description. These are owner costs for reporting.

### Inspections

Open Inspections, select a tenancy, choose move-in or move-out, set the inspection date and choose whether it is visible to the tenant. Add checklist items with conditions and notes; attach optional PDF/JPEG/PNG evidence up to 10 MB. Complete the inspection after each checklist item has a condition. Completed inspections and evidence are locked. Tenants can only view inspections marked as shared with them.

### Maintenance

Tenants submit maintenance requests from their portal by selecting an active tenancy and entering a subject and description. Owners open Maintenance to review requests and change their status among open, in progress, resolved and closed. Requests are not currently sent by email or WhatsApp.

### Reports and CSV exports

Open Reports & exports or use the dashboard shortcut. Select this month, last month or this quarter, then download rent charges, payments, expenses, utility bills or deposit transactions as CSV. Exports are owner-only, bounded to the selected period and capped at 10,000 rows. If a download reaches that cap, use a shorter period.

## 3. Tenant portal

Tenants use the same frontend URL and sign in with the account they created through the invitation. The portal provides:

- Linked tenancy details and posted charges/balances.
- Recorded payments, status and printable receipts; unallocated credits are shown.
- Security deposit balance and transaction history.
- Documents and inspections the owner has shared with that tenant.
- Submission and tracking of maintenance requests.
- Notification preferences for email and WhatsApp. Both default off. WhatsApp opt-in requires a phone number in international format (for example, +919876543210). Tenants can revoke consent; opting out removes the saved WhatsApp number.

When configured, the app sends a payment receipt through each opted-in channel after an owner first records a payment. Email uses Resend; WhatsApp uses Meta Cloud API and an approved template. Rent reminders and other notification types are not sent yet. Follow the **Email and WhatsApp setup** section later in this guide to configure the provider accounts, local environment, and approved WhatsApp template.

## 4. API-only operations

Use the interactive API documentation at /docs while signed in as an owner. Browser mutations require the session's CSRF token; the app handles this automatically. For external scripts, include the session cookies and the matching X-CSRF-Token header. Use an Idempotency-Key for payment and deposit transaction creation.

| Operation | Endpoint | Notes |
|---|---|---|
| Post monthly rent | POST /api/tenancies/{tenancy_id}/charges/rent/{billing_month} | billing_month must be the first of the month, e.g. 2026-10-01. Returns the charge ID needed for allocation. A single rent term must cover the billable days. |
| Allocate tenant credit | POST /api/credits/{credit_id}/allocations | JSON body: {"charge_id":"…","amount":"100.00"}. Use the credit_id returned when recording the payment. |
| Close tenancy | POST /api/tenancies/{tenancy_id}/close | JSON body: {"move_out_date":"YYYY-MM-DD"}. The move-out date is exclusive for tenancy membership. |
| View tenant notification preferences | GET /api/tenant/notification-preferences | Tenant session only. |
| Change tenant notification preferences | PUT /api/tenant/notification-preferences | Tenant session and CSRF token required. |

The API also exposes the UI-backed actions for properties, invitations, tenancies, payments, deposits, utilities, inspections, maintenance and reports. /docs is the source of truth for request fields and response schemas.

## 5. Common rules and troubleshooting

- Use the same hostname consistently. If the frontend is opened at http://localhost:5173, keep the backend CORS origin configured as http://localhost:5173; localhost and 127.0.0.1 are different browser origins.
- Ensure the database container is healthy, the .env URL uses host port 5433, and migrations have been applied after code updates.
- If a form shows an error, read the red alert above the form. The API error message often identifies a date, tenancy, balance, authorization, or validation issue.
- Payment received dates must fall within the tenant's tenancy participation dates. Amounts must be positive and use paise precision (at most two decimal places).
- Rent, payment, deposit, utility and expense records use INR. Recorded payments do not automatically settle a charge until a credit allocation is posted.
- For operational gaps, current status and local-development instructions, see the README, progress log, business rules, security checklist, and backup/restore notes.

## 6. Current product limits

This development build has no payment gateway, automatic rent scheduling, automatic tenant-credit allocation, rent reminder or maintenance notifications, owner notifications, automated backups, malware scanning, or production deployment. Payment receipts can use configured email/WhatsApp providers. Utility bills and late fees require owner action. Complete security review, database-backed integration/concurrency tests, backup/restore validation and deployment configuration before using real tenancy or financial data.

