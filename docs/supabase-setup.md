# Supabase setup

The app uses SQLAlchemy and Alembic for PostgreSQL and keeps its own sign-in/authorization checks. Supabase Auth is not required. Supabase is used as the managed PostgreSQL database and as private object storage for tenancy documents and inspection evidence.

## Supabase project and environment

1. Create a Supabase project and set a strong database password.
2. In **Project → Connect**, copy the **Session pooler** connection string. This mode works on IPv4-only networks and supports persistent sessions, which fits this long-running FastAPI backend. Use the host, port, username and database name exactly as shown by Supabase.
3. In the project **Storage** page, create a bucket named `hearth-private` and leave it **Private**. Set a 10 MB file size limit and allow `application/pdf`, `image/jpeg`, and `image/png`.
4. In **Project Settings → API Keys**, create/copy a server-side **secret key**. It bypasses Storage RLS, so it must remain only in the backend environment.
5. In the project root `.env`, set these values while preserving your other settings:

   ~~~dotenv
   DATABASE_URL=postgresql+psycopg://<pooler-user>:<URL-encoded-db-password>@<pooler-host>:5432/postgres?sslmode=require
   PRIVATE_STORAGE_BACKEND=supabase
   SUPABASE_URL=https://<project-ref>.supabase.co
   SUPABASE_SECRET_KEY=sb_secret_...
   SUPABASE_STORAGE_BUCKET=hearth-private
   ~~~

   The connection URI must use the pooler values Supabase provided. URL-encode reserved characters in the database password. Keep the `sslmode=require` query parameter. Do not put the Supabase secret key in a frontend environment variable or paste it into chat.

6. Install the backend dependencies, then apply migrations to the selected Supabase database:

   ~~~powershell
   .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
   Set-Location backend
   ..\.venv\Scripts\python.exe -m alembic upgrade head
   ~~~

7. Start the backend and frontend as usual. On a brand-new empty project, create the first owner with `python -m app.bootstrap_owner` from `backend`. Do not run owner bootstrap if you imported existing application data.

Supabase documents [Postgres connection modes](https://supabase.com/docs/guides/database/connecting-to-postgres), [private buckets](https://supabase.com/docs/guides/storage/buckets/fundamentals), and [server-side API keys](https://supabase.com/docs/guides/getting-started/api-keys).

## Move existing local files

The app does not move files automatically when you switch storage backends. To preserve existing local evidence, stop the backend, configure `PRIVATE_STORAGE_BACKEND=supabase` and the Supabase Storage values above, but keep `DATABASE_URL` pointing at the current local database. Then run from the project root:

~~~powershell
Set-Location backend
..\.venv\Scripts\python.exe -m app.migrate_local_files_to_supabase
~~~

This copies each referenced PDF/image to the private bucket using its existing storage key. It leaves local files and database rows intact, and can be rerun. After the database rows have been migrated, change `DATABASE_URL` to Supabase and start the app.

## Move existing database records

Changing `DATABASE_URL` points the app at another database; it does not copy existing users, tenancies, ledger rows, or invitations. Keep a verified local backup before moving records. For a new/empty Supabase database, apply Alembic migrations first, then migrate the application's table data with PostgreSQL's `pg_dump`/`pg_restore` using `--data-only`, `--no-owner`, and `--no-privileges`; exclude `public.alembic_version` (the target migration already created it) and `public.login_sessions` (users should sign in again). Use the Supabase pooler URI for the target and keep credentials out of shell history. Reconcile table counts and verify an owner login, tenant access, document downloads, and inspection evidence before retiring the local database.

If Supabase already has data or this is not a new/empty project, stop and plan a schema-aware migration first. Do not run a restore with `--clean` against a Supabase project you need to keep.

## File access and backups

Downloads continue through the app's authenticated endpoints. The app checks owner/tenant access before it fetches the object; it does not create a public bucket or expose signed URLs to the browser. Keep the server secret key restricted to the backend and rotate it if it is exposed.

Database backups do not contain Storage object bytes. Back up and restore the database and private bucket separately, then verify both metadata rows and the corresponding objects. Supabase Storage exposes an S3-compatible interface for bulk backup tooling; see [download objects](https://supabase.com/docs/guides/storage/management/download-objects).
