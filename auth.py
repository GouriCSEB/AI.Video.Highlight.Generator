"""
auth.py — User authentication for HILIGHT
Now uses PostgreSQL via SQLAlchemy (replaces users.json)
"""

from functools import wraps
from flask import session, redirect, url_for, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from database import db, User


def create_user(name: str, email: str, password: str) -> dict:
    email = email.strip().lower()
    name  = name.strip()
    if not name or not email or not password:
        return {"ok": False, "error": "All fields are required."}
    if len(password) < 6:
        return {"ok": False, "error": "Password must be at least 6 characters."}
    if "@" not in email or "." not in email:
        return {"ok": False, "error": "Invalid email address."}
    if User.query.filter_by(email=email).first():
        return {"ok": False, "error": "An account with this email already exists."}
    user = User(name=name, email=email,
                password_hash=generate_password_hash(password),
                avatar=name[0].upper())
    db.session.add(user)
    db.session.commit()
    return {"ok": True, "user": user.to_dict()}


def login_user_by_email(email: str, password: str) -> dict:
    email = email.strip().lower()
    user  = User.query.filter_by(email=email).first()
    if not user:
        return {"ok": False, "error": "No account found with this email."}
    if not check_password_hash(user.password_hash, password):
        return {"ok": False, "error": "Incorrect password."}
    if not user.is_active:
        return {"ok": False, "error": "This account has been deactivated."}
    return {"ok": True, "user": user.to_dict()}


def get_user_by_id(user_id: str) -> dict | None:
    user = User.query.get(user_id)
    return user.to_dict() if user else None


def login_session(user: dict):
    session.permanent = True
    session["user_id"]    = user["id"]
    session["user_name"]  = user["name"]
    session["user_email"] = user["email"]
    session["avatar"]     = user.get("avatar", user["name"][0].upper())


def logout_session():
    session.clear()


def current_user() -> dict | None:
    uid = session.get("user_id")
    return get_user_by_id(uid) if uid else None


def is_logged_in() -> bool:
    return bool(session.get("user_id"))


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_logged_in():
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"error": "Login required", "redirect": "/login"}), 401
            return redirect(url_for("login_page") + f"?next={request.path}")
        return f(*args, **kwargs)
    return decorated
