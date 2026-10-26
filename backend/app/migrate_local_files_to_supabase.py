"""Copy existing local tenancy documents and inspection evidence to Supabase Storage.

Run while DATABASE_URL still points to the source PostgreSQL database, with
PRIVATE_STORAGE_BACKEND=supabase and Supabase Storage credentials configured.
The script never deletes local files or changes database rows.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import engine
from app.file_storage import PrivateStorageError, copy_local_file_to_supabase
from app.models import InspectionMedia, TenancyDocument
from app.settings import settings


def main() -> None:
    if settings.private_storage_backend != "supabase":
        raise SystemExit("Set PRIVATE_STORAGE_BACKEND=supabase before running this migration")

    storage_dir = settings.private_storage_dir.resolve()
    with Session(engine) as db:
        files = list(db.execute(select(TenancyDocument.storage_key, TenancyDocument.content_type)))
        files.extend(db.execute(select(InspectionMedia.storage_key, InspectionMedia.content_type)))

    total = len(files)
    for index, (storage_key, content_type) in enumerate(files, start=1):
        source_path = (storage_dir / storage_key).resolve()
        if source_path.parent != storage_dir or not source_path.is_file():
            raise SystemExit(f"Local file missing or invalid for stored key: {storage_key}")
        try:
            copy_local_file_to_supabase(storage_key, source_path, content_type)
        except PrivateStorageError as exc:
            raise SystemExit(f"Upload failed for stored key {storage_key}: {exc}") from exc
        print(f"Copied {index}/{total} private files")

    print(f"Finished: {total} files copied. Local originals remain in place.")


if __name__ == "__main__":
    main()
