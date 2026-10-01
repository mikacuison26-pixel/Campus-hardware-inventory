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
import smtplib
import random
from email.mime.text import MIMEText


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is required. Configure the Supabase PostgreSQL connection in .env."
    )

# --- BREVO SMTP CONFIGURATION ---
SMTP_SERVER = "smtp-relay.brevo.com"
SMTP_PORT = 2525

SMTP_LOGIN = os.getenv("BREVO_SMTP_LOGIN")
SMTP_PASSWORD = os.getenv("BREVO_SMTP_PASSWORD")
SMTP_SENDER = os.getenv("BREVO_SENDER_EMAIL")

def send_otp_email(receiver_email, otp, intent):
    """Sends a 6-digit OTP using Brevo SMTP."""

    msg = MIMEText(
        f"Your {intent} One-Time Password (OTP) is: {otp}\n\n"
        "Please enter this code to proceed. Do not share this code with anyone."
    )

    msg["Subject"] = f"Laboratory System - {intent} OTP"
    msg["From"] = SMTP_SENDER
    msg["To"] = receiver_email

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_LOGIN, SMTP_PASSWORD)
            server.send_message(msg)

        print(f"OTP email sent to {receiver_email}")
        return True

    except Exception as e:
        print(f"Email Error: {e}")
        return False


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
    if request.method == "GET":
        return render_template("register.html")

    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "").strip()
    role = request.form.get("role", "USER").strip().upper()

    if not username or not email or not password:
        flash("All registration fields are required.", "danger")
        return redirect(url_for("register"))

    # Generate OTP and save to session
    otp = str(random.randint(100000, 999999))
    session['pending_user'] = {
        'username': username, 'email': email, 'password': password, 'role': role, 'otp': otp}

    if send_otp_email(email, otp, intent="Account Registration"):
        flash("We sent a 6-digit code to your email. Please verify.", "info")
        return redirect(url_for("verify_otp", action="register"))
    else:
        flash("Failed to send OTP email. Please try again.", "danger")
        return redirect(url_for("register"))


@app.route("/reset-request", methods=["GET", "POST"])
def reset_request():
    if request.method == "GET":
        return render_template("reset.html")

    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip()
    new_password = request.form.get("password", "").strip()
    confirm_password = request.form.get("confirm_password", "").strip()

    if not username or not email or not new_password or not confirm_password:
        flash("All reset fields are required.", "danger")
        return redirect(url_for("reset_request"))

    if new_password != confirm_password:
        flash("New passwords do not match.", "danger")
        return redirect(url_for("reset_request"))

    # Generate OTP and save to session
    otp = str(random.randint(100000, 999999))

    session["pending_reset"] = {
        "username": username,
        "email": email,
        "new_password": new_password,
        "otp": otp
    }

    if send_otp_email(email, otp, intent="Password Reset"):
        flash(
            "We sent a 6-digit code to your email. Please verify.",
            "info"
        )
        return redirect(url_for("verify_otp", action="reset"))

    else:
        flash(
            "Failed to send OTP email. Please try again.",
            "danger"
        )
        return redirect(url_for("reset_request"))


@app.route("/verify-otp/<action>", methods=["GET", "POST"])
def verify_otp(action):
    # Determine which session data to use
    session_key = 'pending_user' if action == "register" else 'pending_reset'

    if session_key not in session:
        flash("Session expired. Please try again.", "warning")
        return redirect(url_for("login"))

    if request.method == "POST":
        user_otp = request.form.get("otp_code", "").strip()
        data = session[session_key]

        if user_otp == data['otp']:
            if action == "register":
                # OTP matches, create the user
                ok, msg = AuthController.register_user(
                    data['username'], data['email'], data['password'], role=data['role'])
                session.pop(session_key, None)
                flash("Account successfully verified and created!",
                      "success" if ok else "warning")
                return redirect(url_for("login"))

            elif action == "reset":
                # OTP matches, submit the reset request to Admin
                ok, msg = AuthController.submit_password_reset_request(
                    data['username'], data['email'], data['new_password'])
                session.pop(session_key, None)
                flash("Email verified! Your password reset request has been submitted.",
                      "success" if ok else "danger")
                return redirect(url_for("login"))
        else:
            flash("Invalid OTP code. Try again.", "danger")

    return render_template("otp_verify.html", action_url=url_for('verify_otp', action=action))


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
