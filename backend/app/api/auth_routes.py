import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session as DbSession

from ..auth import ROLE_LEVELS, create_token, hash_password, verify_password
from ..config import settings
from ..database import SessionLocal
from ..models import User
from ..schemas import (LoginRequest, SignupRequest, TokenResponse, UserCreate,
                       UserOut, UserRoleUpdate)
from ..security import (AuthContext, audit, client_ip, get_current_user,
                        login_limiter, require_role)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def seed_admin() -> None:
    """Create the initial admin account if no users exist."""
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            db.add(User(username=settings.ADMIN_USERNAME,
                        password_hash=hash_password(settings.ADMIN_PASSWORD),
                        role="admin"))
            db.commit()
            log.warning("Seeded initial admin user '%s' — change its password "
                        "via ADMIN_PASSWORD before deploying",
                        settings.ADMIN_USERNAME)
    finally:
        db.close()


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: DbSession = Depends(get_db)):
    ip = client_ip(request)
    if not login_limiter.allow(ip):
        raise HTTPException(status_code=429, detail="Too many login attempts")
    from sqlalchemy import func
    user = (db.query(User)
            .filter(func.lower(User.username) == body.username.strip().lower())
            .first())
    if user is None or not verify_password(body.password, user.password_hash):
        audit(db, body.username, "login_failed", f"ip={ip}")
        raise HTTPException(status_code=401, detail="Invalid username or password")
    claims = {"sub": user.username, "role": user.role}
    from ..models import Student
    student = db.query(Student).filter(Student.user_id == user.id).first()
    if student is not None:
        claims["student_id"] = student.id
    token = create_token(claims, settings.JWT_SECRET, settings.JWT_EXPIRES_MINUTES)
    audit(db, user.username, "login", f"ip={ip}")
    return TokenResponse(token=token, username=user.username, role=user.role,
                         expires_in=settings.JWT_EXPIRES_MINUTES * 60,
                         student_id=student.id if student else None)


@router.post("/signup", response_model=TokenResponse, status_code=201)
def signup(body: SignupRequest, request: Request, db: DbSession = Depends(get_db)):
    """Self-registration. New accounts get the lowest role (viewer);
    an admin promotes them from the Users page."""
    ip = client_ip(request)
    if not login_limiter.allow(ip):
        raise HTTPException(status_code=429, detail="Too many attempts")
    username = body.username.strip().lower()
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=409,
                            detail="That username is already taken")
    # default to viewer; an admin signup code (if configured) grants admin
    role = "viewer"
    if body.admin_code:
        if (settings.ADMIN_SIGNUP_CODE
                and body.admin_code == settings.ADMIN_SIGNUP_CODE):
            role = "admin"
        else:
            raise HTTPException(status_code=403, detail="Invalid admin code")
    user = User(username=username, password_hash=hash_password(body.password),
                role=role)
    db.add(user)
    db.commit()
    audit(db, username, "signup", f"ip={ip} role={role}")
    token = create_token({"sub": user.username, "role": user.role},
                         settings.JWT_SECRET, settings.JWT_EXPIRES_MINUTES)
    return TokenResponse(token=token, username=user.username, role=user.role,
                         expires_in=settings.JWT_EXPIRES_MINUTES * 60)


@router.get("/me")
def me(user: AuthContext = Depends(get_current_user)):
    return {"username": user.username, "role": user.role,
            "student_id": user.student_id}


@router.get("/users", response_model=List[UserOut])
def list_users(db: DbSession = Depends(get_db),
               _: AuthContext = Depends(require_role("admin"))):
    return db.query(User).order_by(User.id).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, db: DbSession = Depends(get_db),
                actor: AuthContext = Depends(require_role("admin"))):
    if body.role not in ROLE_LEVELS:
        raise HTTPException(status_code=422, detail="Invalid role")
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=409, detail="Username already exists")
    user = User(username=body.username, password_hash=hash_password(body.password),
                role=body.role)
    db.add(user)
    db.commit()
    db.refresh(user)
    audit(db, actor.username, "user_created", f"{body.username} ({body.role})")
    return user


@router.put("/users/{user_id}", response_model=UserOut)
def change_role(user_id: int, body: UserRoleUpdate,
                db: DbSession = Depends(get_db),
                actor: AuthContext = Depends(require_role("admin"))):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.username == actor.username and body.role != "admin":
        raise HTTPException(status_code=409, detail="Cannot demote your own account")
    old = user.role
    user.role = body.role
    db.commit()
    db.refresh(user)
    audit(db, actor.username, "user_role_changed",
          f"{user.username}: {old} -> {body.role}")
    return user


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, db: DbSession = Depends(get_db),
                actor: AuthContext = Depends(require_role("admin"))):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.username == actor.username:
        raise HTTPException(status_code=409, detail="Cannot delete your own account")
    db.delete(user)
    db.commit()
    audit(db, actor.username, "user_deleted", user.username)
