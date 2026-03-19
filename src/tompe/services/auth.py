"""Authentication service for ToM-PE v1.

Simple username/password authentication with bcrypt hashing and token-based
sessions. Teacher app runs on localhost and is implicitly authenticated (v1).
"""

import csv
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from uuid import uuid4

import bcrypt
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from tompe.schemas.enums import AnnotationLevel
from tompe.schemas.session import ClassGroup, SessionToken, StudentAccount
from tompe.services.datastore import classes_store, students_store, tokens_store

security = HTTPBearer(auto_error=False)

# Token validity: 7 days
TOKEN_EXPIRY_HOURS = 168


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


# ── Account management ────────────────────────────────────────────────────────


def create_account(
    username: str,
    display_name: str,
    password: str,
    class_id: str,
    current_level: AnnotationLevel = AnnotationLevel.NAVIGATOR,
    allowed_levels: Optional[list[AnnotationLevel]] = None,
) -> StudentAccount:
    """Create a new student account."""
    # Check uniqueness
    existing = students_store.list_all(
        StudentAccount, filter_fn=lambda s: s.username == username
    )
    if existing:
        raise ValueError(f"Username '{username}' already exists")

    account = StudentAccount(
        student_id=str(uuid4()),
        username=username,
        display_name=display_name,
        password_hash=_hash_password(password),
        class_id=class_id,
        current_level=current_level,
        allowed_levels=allowed_levels or [AnnotationLevel.NAVIGATOR],
    )
    students_store.save(account)
    return account


def bulk_import_csv(csv_path: str | Path, class_id: str) -> list[StudentAccount]:
    """Import student accounts from CSV (columns: username, display_name, password)."""
    accounts = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                account = create_account(
                    username=row["username"].strip(),
                    display_name=row["display_name"].strip(),
                    password=row["password"].strip(),
                    class_id=class_id,
                )
                accounts.append(account)
            except ValueError:
                continue  # Skip duplicates
    return accounts


def get_student(student_id: str) -> Optional[StudentAccount]:
    """Retrieve a student account by ID."""
    return students_store.get(student_id, StudentAccount)


def list_students(class_id: Optional[str] = None) -> list[StudentAccount]:
    """List student accounts, optionally filtered by class."""
    if class_id:
        return students_store.list_all(
            StudentAccount, filter_fn=lambda s: s.class_id == class_id
        )
    return students_store.list_all(StudentAccount)


def update_student_levels(
    student_id: str,
    current_level: Optional[AnnotationLevel] = None,
    allowed_levels: Optional[list[AnnotationLevel]] = None,
) -> Optional[StudentAccount]:
    """Update a student's level configuration."""
    patch: dict = {}
    if current_level is not None:
        patch["current_level"] = current_level
    if allowed_levels is not None:
        patch["allowed_levels"] = allowed_levels
    return students_store.update(student_id, StudentAccount, patch)


# ── Class management ──────────────────────────────────────────────────────────


def create_class(class_name: str, default_levels: Optional[list[AnnotationLevel]] = None) -> ClassGroup:
    """Create a new class group."""
    cls = ClassGroup(
        class_id=str(uuid4()),
        class_name=class_name,
        default_levels=default_levels or [AnnotationLevel.NAVIGATOR],
    )
    classes_store.save(cls)
    return cls


def list_classes() -> list[ClassGroup]:
    """List all class groups."""
    return classes_store.list_all(ClassGroup)


def get_class(class_id: str) -> Optional[ClassGroup]:
    """Get a class group by ID."""
    return classes_store.get(class_id, ClassGroup)


# ── Authentication ────────────────────────────────────────────────────────────


def authenticate(username: str, password: str) -> tuple[StudentAccount, str]:
    """Authenticate a student. Returns (account, token) or raises ValueError."""
    matches = students_store.list_all(
        StudentAccount, filter_fn=lambda s: s.username == username and s.is_active
    )
    if not matches:
        raise ValueError("Invalid username or password")

    account = matches[0]
    if not _verify_password(password, account.password_hash):
        raise ValueError("Invalid username or password")

    # Create session token
    token = secrets.token_hex(32)
    session = SessionToken(
        token=token,
        student_id=account.student_id,
        expires_at=datetime.now() + timedelta(hours=TOKEN_EXPIRY_HOURS),
    )
    tokens_store.save(session)
    return account, token


def validate_token(token: str) -> Optional[StudentAccount]:
    """Validate a session token. Returns the account or None."""
    session = tokens_store.get(token, SessionToken)
    if session is None:
        return None
    if session.expires_at and session.expires_at < datetime.now():
        tokens_store.delete(token)
        return None
    return students_store.get(session.student_id, StudentAccount)


def invalidate_token(token: str) -> bool:
    """Invalidate (logout) a session token."""
    return tokens_store.delete(token)


# ── FastAPI dependency ────────────────────────────────────────────────────────


async def verify_token(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
) -> StudentAccount:
    """FastAPI dependency: verify bearer token and return student account."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing authentication token")

    account = validate_token(credentials.credentials)
    if account is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return account
