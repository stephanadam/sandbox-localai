import bcrypt
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except ValueError:
        return False


def login_user(request: Request, user: User) -> None:
    request.session["user_id"] = user.id


def logout_user(request: Request) -> None:
    request.session.clear()


def get_current_user(
    request: Request, db: Session = Depends(get_db)
) -> User | None:
    """Return the logged-in user, or None if not authenticated."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get(User, user_id)
