from controllers.hardware_controller import HardwareController
from controllers.auth_controller import AuthController
from logger import logger
from flask import Flask, flash, redirect, render_template, request, session, url_for
from dotenv import load_dotenv
from pathlib import Path
from functools import wraps
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
import os
import psycopg


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is required. Configure the Supabase PostgreSQL connection in .env."
    )

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "lab7-development-secret")
logger.info("Using Supabase PostgreSQL as the live application database.")


@app.template_filter("localtime")
def format_localtime(value):
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    if value.tzinfo is not None:
        value = value.astimezone(ZoneInfo("Asia/Manila"))
    return value.strftime("%Y-%m-%d %H:%M:%S")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "username" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("role") != "ADMIN":
            flash("Administrator access required.", "danger")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)

    return wrapped


def controllers():
    return AuthController(), HardwareController()


# ============================================================
# TEMPORARY DATABASE DIAGNOSTIC
# Remove this route after we finish troubleshooting.
# ============================================================

@app.route("/__dbcheck")
def db_check():
    try:
        parsed = urlparse(DATABASE_URL)

        conn = psycopg.connect(DATABASE_URL)
        cur = conn.cursor()

        # Count users in the PostgreSQL database
        cur.execute("SELECT COUNT(*) FROM users")
        user_count = cur.fetchone()[0]

        # Check whether the admin account exists
        cur.execute(
            """
            SELECT username, email, role, is_locked
            FROM users
            WHERE LOWER(username) = LOWER(%s)
            """,
            ("admin",)
        )

        admin = cur.fetchone()

        cur.close()
        conn.close()

        return {
            "database_connection": "OK",
            "database_host": parsed.hostname,
            "database_name": parsed.path.lstrip("/"),
            "users_count": user_count,
            "admin_exists": admin is not None,
            "admin_username": admin[0] if admin else None,
            "admin_email": admin[1] if admin else None,
            "admin_role": admin[2] if admin else None,
            "admin_locked": admin[3] if admin else None,
        }

    except Exception as e:
        return {
            "database_connection": "FAILED",
            "error_type": type(e).__name__,
            "error": str(e),
        }, 500


@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        auth, _ = controllers()

        ok, message, user = auth.login_user(
            request.form.get("username", ""),
            request.form.get("password", "")
        )

        if ok:
            session.clear()
            session.update(
                username=user["username"],
                email=user["email"],
                role=user["role"].upper()
            )
            return redirect(url_for("dashboard"))

        flash(message, "danger")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        auth, _ = controllers()

        ok, message = auth.register_user(
            request.form.get("username", ""),
            request.form.get("email", ""),
            request.form.get("password", ""),
            request.form.get("role", "USER")
        )

        flash(message, "success" if ok else "danger")

        if ok:
            return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/reset", methods=["GET", "POST"])
def reset():
    if request.method == "POST":
        auth, _ = controllers()

        password = request.form.get("password", "")

        if password != request.form.get("confirm_password", ""):
            flash("Passwords do not match.", "danger")
        else:
            ok, message = auth.request_password_reset(
                request.form.get("username", ""),
                request.form.get("email", ""),
                password
            )

            flash(message, "success" if ok else "danger")

            if ok:
                return redirect(url_for("login"))

    return render_template("reset.html")


@app.route("/dashboard")
@login_required
def dashboard():
    if session["role"] != "ADMIN":
        return redirect(url_for("catalog"))

    return redirect(url_for("admin_catalog"))


@app.route("/admin/catalog")
@admin_required
def admin_catalog():
    _, hardware = controllers()

    search_term = request.args.get("q", "").strip()

    return render_template(
        "admin_catalog.html",
        rows=hardware.fetch_all_records(search_term),
        search_term=search_term,
        total_stocks=hardware.get_total_stocks(),
    )


@app.route("/admin/requests")
@admin_required
def admin_requests():
    auth, hardware = controllers()

    return render_template(
        "admin_requests.html",
        borrowed=hardware.get_borrowed_items(),
        pending_borrows=hardware.get_pending_borrow_requests(),
        pending_returns=hardware.get_pending_return_requests(),
        reset_requests=auth.fetch_pending_reset_requests(),
    )


@app.route("/catalog")
@login_required
def catalog():
    _, hardware = controllers()

    search_term = request.args.get("q", "").strip()

    return render_template(
        "catalog.html",
        rows=hardware.fetch_all_records(search_term),
        search_term=search_term,
        total_stocks=hardware.get_total_stocks(),
    )


@app.route("/borrow-page")
@login_required
def borrow_page():
    _, hardware = controllers()

    borrowed = hardware.get_borrowed_items(
        student_name=session["username"]
    )

    return render_template(
        "borrow.html",
        rows=hardware.fetch_all_records(),
        borrowed=borrowed,
        student_id=session.get("student_id", ""),
    )


@app.route("/history")
@login_required
def history_page():
    _, hardware = controllers()

    is_admin = session.get("role") == "ADMIN"

    history = hardware.get_history_records(
        student_name=session["username"] if not is_admin else None
    )

    return render_template(
        "history.html",
        history=history,
        is_admin=is_admin,
    )


@app.post("/borrow")
@login_required
def borrow():
    _, hardware = controllers()

    student_id = request.form.get("student_id", "").strip()

    ok, message = hardware.request_borrow(
        request.form.get("item_id"),
        student_id,
        request.form.get("quantity"),
        session["username"]
    )

    if ok:
        session["student_id"] = student_id

    flash(message, "success" if ok else "danger")

    return redirect(url_for("borrow_page"))


@app.post("/return/<int:item_id>")
@login_required
def request_return(item_id):
    _, hardware = controllers()

    student_id = session.get("student_id", "").strip()

    ok, message = hardware.request_return_quantity(
        item_id,
        student_id,
        session["username"],
        request.form.get("quantity"),
    )

    flash(message, "success" if ok else "danger")

    return redirect(url_for("borrow_page"))


@app.post("/admin/add")
@admin_required
def add_hardware():
    _, hardware = controllers()

    ok, message = hardware.add_hardware(
        request.form.get("item_name", "").strip(),
        request.form.get("category", "").strip(),
        request.form.get("quantity", ""),
        request.form.get("unit_price", "")
    )

    flash(message, "success" if ok else "danger")

    return redirect(url_for("admin_catalog"))


@app.post("/admin/update/<int:item_id>")
@admin_required
def update_hardware(item_id):
    _, hardware = controllers()

    ok, message = hardware.update_hardware(
        item_id,
        request.form.get("quantity", ""),
        request.form.get("unit_price", ""),
    )

    flash(message, "success" if ok else "danger")

    return redirect(url_for("admin_catalog"))


@app.post("/admin/borrow/<int:request_id>/<action>")
@admin_required
def approve_borrow(request_id, action):
    _, hardware = controllers()

    ok, message = hardware.approve_borrow_request(
        request_id,
        action == "approve"
    )

    flash(message, "success" if ok else "danger")

    return redirect(url_for("admin_requests"))


@app.post("/admin/return/<int:request_id>/<action>")
@admin_required
def approve_return(request_id, action):
    _, hardware = controllers()

    ok, message = hardware.approve_return_request(
        request_id,
        action == "approve"
    )

    flash(message, "success" if ok else "danger")

    return redirect(url_for("admin_requests"))


@app.post("/admin/reset/<int:request_id>/<action>")
@admin_required
def process_reset(request_id, action):
    auth, _ = controllers()

    ok, message = auth.process_reset_request(
        request_id,
        action == "approve"
    )

    flash(message, "success" if ok else "danger")

    return redirect(url_for("admin_requests"))


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)
