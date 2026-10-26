"""Private file storage with local and Supabase Storage backends."""

import logging
import os
from functools import lru_cache
from pathlib import Path

from app.settings import settings

logger = logging.getLogger(__name__)


class PrivateStorageError(RuntimeError):
    """A private file operation failed without exposing provider details to the caller."""


def _validate_supabase_configuration() -> None:
    if not settings.supabase_url or not settings.supabase_secret_key:
        raise PrivateStorageError("Supabase Storage is selected but its server configuration is incomplete")


@lru_cache(maxsize=1)
def _supabase_client():
    _validate_supabase_configuration()
    try:
        from supabase import create_client
        from supabase.lib.client_options import ClientOptions

        return create_client(
            settings.supabase_url,
            settings.supabase_secret_key,
            options=ClientOptions(auto_refresh_token=False, persist_session=False),
        )
    except Exception as exc:
        logger.exception("Could not initialize Supabase Storage client")
        raise PrivateStorageError("Could not initialize private file storage") from exc


def save_private_file(storage_key: str, temp_path: Path, content_type: str) -> None:
    """Move a validated staged file into local storage or upload it to a private bucket."""
    try:
        if settings.private_storage_backend == "local":
            storage_dir = settings.private_storage_dir.resolve()
            storage_dir.mkdir(parents=True, exist_ok=True)
            final_path = (storage_dir / storage_key).resolve()
            if final_path.parent != storage_dir:
                raise PrivateStorageError("Invalid private file key")
            os.replace(temp_path, final_path)
            return

        content = temp_path.read_bytes()
        _supabase_client().storage.from_(settings.supabase_storage_bucket).upload(
            path=storage_key,
            file=content,
            file_options={"content-type": content_type, "upsert": "false"},
        )
    except PrivateStorageError:
        raise
    except Exception as exc:
        logger.warning("Private file upload failed for key=%s", storage_key)
        raise PrivateStorageError("Could not save the uploaded file") from exc
    finally:
        if settings.private_storage_backend == "supabase":
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not remove temporary upload file")


def copy_local_file_to_supabase(storage_key: str, source_path: Path, content_type: str) -> None:
    """Copy an existing local object to Supabase without removing the source file."""
    if settings.private_storage_backend != "supabase":
        raise PrivateStorageError("Set PRIVATE_STORAGE_BACKEND=supabase before migrating local files")
    try:
        _supabase_client().storage.from_(settings.supabase_storage_bucket).upload(
            path=storage_key,
            file=source_path.read_bytes(),
            file_options={"content-type": content_type, "upsert": "true"},
        )
    except Exception as exc:
        logger.warning("Private file migration failed for key=%s", storage_key)
        raise PrivateStorageError("Could not copy a local file to Supabase Storage") from exc


def read_private_file(storage_key: str) -> bytes:
    """Read a file only after the API layer has authorized the requesting user."""
    try:
        if settings.private_storage_backend == "local":
            storage_dir = settings.private_storage_dir.resolve()
            path = (storage_dir / storage_key).resolve()
            if path.parent != storage_dir or not path.is_file():
                raise FileNotFoundError(storage_key)
            return path.read_bytes()

        return _supabase_client().storage.from_(settings.supabase_storage_bucket).download(storage_key)
    except FileNotFoundError:
        raise
    except Exception as exc:
        logger.warning("Private file download failed for key=%s", storage_key)
        raise PrivateStorageError("Could not retrieve the requested file") from exc


def delete_private_file(storage_key: str) -> None:
    """Best-effort rollback cleanup after an object was stored but its DB row failed."""
    try:
        if settings.private_storage_backend == "local":
            storage_dir = settings.private_storage_dir.resolve()
            path = (storage_dir / storage_key).resolve()
            if path.parent == storage_dir:
                path.unlink(missing_ok=True)
            return

        _supabase_client().storage.from_(settings.supabase_storage_bucket).remove([storage_key])
    except Exception:
        logger.exception("Could not clean up private file after database failure; key=%s", storage_key)
