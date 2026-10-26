"""Create the initial owner interactively. Run only on a fresh installation."""
import getpass

from sqlalchemy import func, select
from pydantic import EmailStr, TypeAdapter

from app.database import SessionLocal
from app.models import Role, User
from app.api import password_hasher


def main() -> None:
    email = str(TypeAdapter(EmailStr).validate_python(input("Owner email: ").strip())).lower()
    password = getpass.getpass("Owner password (minimum 8 characters): ")
    confirm = getpass.getpass("Confirm password: ")
    if len(password) < 8 or password != confirm:
        raise SystemExit("Password confirmation failed or password is too short.")
    with SessionLocal.begin() as db:
        if db.scalar(select(func.count()).select_from(User).where(User.role == Role.owner)):
            raise SystemExit("An owner already exists; bootstrap is allowed only once.")
        db.add(User(email=email, password_hash=password_hasher.hash(password), role=Role.owner))
    print("Owner account created. Keep the credentials private.")


if __name__ == "__main__":
    main()
