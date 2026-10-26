# Security checklist

## Identity and authorization

- [ ] No public account registration; first owner is created only by secure CLI bootstrap.
- [ ] Hash passwords with Argon2id; store only hashed, expiring, single-use invitation tokens.
- [ ] Use secure HttpOnly SameSite cookies, CSRF protection, session rotation and revocation.
- [ ] Deny by default; verify role and ownership on every API object read/write/export/download.
- [ ] Resolve tenant access from authenticated user and explicit active tenancy membership.
- [ ] Rate-limit login, invitation acceptance, recovery and expensive operations.

## Data and financial integrity

- [ ] Use parameterized SQL, explicit writable schemas and bounded pagination.
- [x] Bound CSV exports, restrict them to owners, and neutralize spreadsheet formula prefixes.
- [ ] Use Decimal and PostgreSQL NUMERIC for all money; centralize currency rounding.
- [ ] Post financial changes transactionally and immutably; use reversals/adjustments.
- [ ] Prevent duplicate charges and allocations through idempotency and database constraints/locking.
- [ ] Prevent overlapping unit tenancies and reconcile utility allocations before posting.
- [ ] Keep audit records minimal, append-only, actor-attributed, and free of secrets.

## Web, uploads and operations

- [ ] Restrict CORS; configure HTTPS, security headers, request limits and safe errors.
- [x] Validate upload size, detected content type/signature, opaque storage key and authorization; keep storage private. Malware scanning remains outstanding.
- [ ] Escape notification content; WhatsApp requires configured provider and recorded opt-in.
- [ ] Avoid personal/financial data, tokens and document contents in logs or previews.
- [ ] Keep secrets out of source control; scan dependencies and document backup, retention and incident response.
- [ ] Run tests against disposable databases and use synthetic data only.

Items are checked only after implementation and verification, not merely because they are planned.
