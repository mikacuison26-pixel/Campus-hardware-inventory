from models.schemas import UserAuthSchema
from logger import logger
import os
import sqlite3
import sys
from pathlib import Path

import bcrypt
import psycopg
from dotenv import load_dotenv
from pydantic import ValidationError

sys.path.append(str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


DATABASE_URL = os.getenv("DATABASE_URL")


def get_postgres_connection():
    if not DATABASE_URL:
        return None
    return psycopg.connect(DATABASE_URL)


def sync_user_to_supabase(user_id=None, username=None, email=None, password_hash=None, role="USER", failed_attempts=0, is_locked=0):
    if not DATABASE_URL:
        return
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (id, username, email, password_hash, role, failed_attempts, is_locked)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        username = EXCLUDED.username,
                        email = EXCLUDED.email,
                        password_hash = EXCLUDED.password_hash,
                        role = EXCLUDED.role,
                        failed_attempts = EXCLUDED.failed_attempts,
                        is_locked = EXCLUDED.is_locked
                    """,
                    (user_id, username, email, password_hash,
                     role, failed_attempts, is_locked),
                )
    except Exception as exc:
        logger.warning(f"Supabase user sync warning: {exc}")


def sync_reset_request_to_supabase(request_id=None, email=None, new_password_hash=None, status="PENDING"):
    if not DATABASE_URL:
        return
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                if request_id is not None:
                    cur.execute(
                        """
                        INSERT INTO password_resets (id, email, desired_password_hash, status)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            email = EXCLUDED.email,
                            desired_password_hash = EXCLUDED.desired_password_hash,
                            status = EXCLUDED.status
                        """,
                        (request_id, email, new_password_hash, status),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO password_resets (email, desired_password_hash, status)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        (email, new_password_hash, status),
                    )
    except Exception as exc:
        logger.warning(f"Supabase password reset sync warning: {exc}")


class AuthController:
    def __init__(self, db_name="hardware_inventory.db"):
        self.db_name = db_name
        self.init_db()

    def init_db(self):
        """Ensures the users and reset_requests tables exist with proper schema."""
        if DATABASE_URL:
            return
        conn = None
        try:
            conn = sqlite3.connect(self.db_name, timeout=10)
            cursor = conn.cursor()

            # Users table with role, failed_attempts, and lockout flag
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT DEFAULT 'USER',
                    failed_attempts INTEGER DEFAULT 0,
                    is_locked INTEGER DEFAULT 0
                )
            """)

            # Table for Task 2 Admin Approvals
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reset_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    new_password_hash TEXT NOT NULL,
                    status TEXT DEFAULT 'PENDING',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database initialization error: {e}")
        finally:
            if conn:
                conn.close()

    def register_user(self, username, email, password, role="USER"):
        try:
            validated = UserAuthSchema(
                username=username, email=email, password=password, role=role)
        except ValidationError as e:
            raw_msg = e.errors()[0]['msg']
            clean_msg = raw_msg.removeprefix("Value error, ")
            logger.warning(f"Registration validation error: {clean_msg}")
            return False, f"Validation Error: {clean_msg}"

        hashed_pw = bcrypt.hashpw(validated.password.encode(
            'utf-8'), bcrypt.gensalt()).decode('utf-8')

        if DATABASE_URL:
            try:
                with get_postgres_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "SELECT COALESCE(MAX(id), 0) + 1 FROM users")
                        user_id = cursor.fetchone()[0]
                        cursor.execute(
                            """
                            INSERT INTO users
                                (id, username, email, password_hash, role, failed_attempts, is_locked)
                            VALUES (%s, %s, %s, %s, %s, 0, 0)
                            """,
                            (user_id, validated.username, validated.email,
                             hashed_pw, validated.role),
                        )
                        logger.info(
                            f"Account created successfully for user: '{validated.username}' with role '{validated.role}'")
                        return True, "Registration successful! You may now log in."
            except psycopg.errors.UniqueViolation as e:
                message = str(e).lower()
                return False, "Email address is already registered." if "email" in message else "Username already taken."
            except Exception as e:
                logger.error(f"Registration database error: {e}")
                return False, f"Database error: {e}"

        conn = None
        try:
            conn = sqlite3.connect(self.db_name, timeout=10)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
                (validated.username, validated.email, hashed_pw, validated.role)
            )
            conn.commit()
            user_id = cursor.lastrowid
            sync_user_to_supabase(
                user_id, validated.username, validated.email, hashed_pw, validated.role, 0, 0)
            logger.info(
                f"Account created successfully for user: '{validated.username}' with role '{validated.role}'")
            return True, "Registration successful! You may now log in."
        except sqlite3.IntegrityError as e:
            err_msg = str(e)
            if "email" in err_msg:
                msg = "Email address is already registered."
            else:
                msg = "Username already taken."
            logger.warning(f"Registration failed: {msg}")
            return False, msg
        finally:
            if conn:
                conn.close()

    def login_user(self, username, password):
        if not username or not password:
            return False, "Please enter both username or email and password.", None

        identifier = username.strip().lower()

        if DATABASE_URL:
            try:
                with get_postgres_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            """
                            SELECT id, username, email, password_hash, role,
                                   failed_attempts, is_locked
                            FROM users
                            WHERE LOWER(username) = %s OR LOWER(email) = %s
                            """,
                            (identifier, identifier),
                        )
                        row = cursor.fetchone()
                        if not row:
                            return False, "Invalid username/email or password.", None

                        user_id, uname, uemail, pwd_hash, role, failed_attempts, is_locked = row
                        if is_locked:
                            return False, "Account is locked due to 3 failed attempts. Please use the Reset Password option.", None

                        if bcrypt.checkpw(password.encode('utf-8'), pwd_hash.encode('utf-8')):
                            cursor.execute(
                                "UPDATE users SET failed_attempts = 0 WHERE id = %s", (user_id,))
                            return True, f"Login successful! Role: {role}", {
                                "id": user_id, "username": uname, "email": uemail, "role": role
                            }

                        new_attempts = failed_attempts + 1
                        locked = new_attempts >= 3
                        cursor.execute(
                            "UPDATE users SET failed_attempts = %s, is_locked = %s WHERE id = %s",
                            (new_attempts, int(locked), user_id),
                        )
                        if locked:
                            return False, "Account locked after 3 failed attempts! Submit a password reset request.", None
                        return False, f"Invalid password. Attempt {new_attempts}/3.", None
            except Exception as e:
                logger.error(f"Login database error: {e}")
                return False, "Unable to complete sign in. Please try again.", None

        conn = None
        try:
            conn = sqlite3.connect(self.db_name, timeout=10)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, username, email, password_hash, role, failed_attempts, is_locked FROM users WHERE LOWER(username) = ? OR LOWER(email) = ?",
                (identifier, identifier)
            )
            row = cursor.fetchone()

            if not row:
                return False, "Invalid username/email or password.", None

            user_id, uname, uemail, pwd_hash, role, failed_attempts, is_locked = row

            if is_locked == 1:
                logger.warning(
                    f"Locked account login attempt for '{identifier}'.")
                return False, "Account is locked due to 3 failed attempts. Please use the Reset Password option.", None

            if bcrypt.checkpw(password.encode('utf-8'), pwd_hash.encode('utf-8')):
                cursor.execute(
                    "UPDATE users SET failed_attempts = 0 WHERE id = ?", (user_id,))
                conn.commit()
                sync_user_to_supabase(
                    user_id, uname, uemail, pwd_hash, role, 0, 0)
                logger.info(f"User '{uname}' logged in successfully.")

                return True, f"Login successful! Role: {role}", {
                    "id": user_id,
                    "username": uname,
                    "email": uemail,
                    "role": role
                }
            else:
                new_attempts = failed_attempts + 1
                if new_attempts >= 3:
                    cursor.execute(
                        "UPDATE users SET failed_attempts = ?, is_locked = 1 WHERE id = ?", (new_attempts, user_id))
                    conn.commit()
                    sync_user_to_supabase(
                        user_id, uname, uemail, pwd_hash, role, new_attempts, 1)
                    logger.warning(
                        f"Account '{uname}' locked after 3 consecutive failed attempts.")
                    return False, "Account locked after 3 failed attempts! Submit a password reset request.", None
                else:
                    cursor.execute(
                        "UPDATE users SET failed_attempts = ? WHERE id = ?", (new_attempts, user_id))
                    conn.commit()
                    sync_user_to_supabase(
                        user_id, uname, uemail, pwd_hash, role, new_attempts, is_locked)
                    logger.warning(
                        f"Failed login attempt ({new_attempts}/3) for user: '{uname}'")
                    return False, f"Invalid password. Attempt {new_attempts}/3.", None
        except sqlite3.Error as e:
            logger.error(f"Login database error: {e}")
            return False, f"Database error: {e}", None
        finally:
            if conn:
                conn.close()

    def update_password_direct(self, username, current_pass, new_pass):
        """Directly updates a user's password from their Profile tab."""
        if not current_pass or not new_pass:
            return False, "Please fill in both current and new password fields."

        if len(new_pass) < 6:
            return False, "New password must be at least 6 characters long."

        if DATABASE_URL:
            try:
                with get_postgres_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "SELECT id, password_hash FROM users WHERE LOWER(username) = %s",
                            (username.strip().lower(),),
                        )
                        row = cursor.fetchone()
                        if not row:
                            return False, "User account not found."
                        user_id, stored_hash = row
                        if not bcrypt.checkpw(current_pass.encode('utf-8'), stored_hash.encode('utf-8')):
                            return False, "Incorrect current password."
                        new_hash = bcrypt.hashpw(new_pass.encode(
                            'utf-8'), bcrypt.gensalt()).decode('utf-8')
                        cursor.execute(
                            "UPDATE users SET password_hash = %s WHERE id = %s",
                            (new_hash, user_id),
                        )
                    conn.commit()
                logger.info(
                    f"Password updated directly for user '{username}'.")
                return True, "Password updated successfully!"
            except Exception as e:
                logger.error(f"Direct password update error: {e}")
                return False, "Password could not be updated. Please try again."

        conn = None
        try:
            conn = sqlite3.connect(self.db_name, timeout=10)
            cursor = conn.cursor()

            # Retrieve user's stored password hash
            cursor.execute(
                "SELECT id, password_hash FROM users WHERE LOWER(username) = ?",
                (username.strip().lower(),)
            )
            row = cursor.fetchone()

            if not row:
                return False, "User account not found."

            user_id, stored_hash = row

            # Verify current password
            if not bcrypt.checkpw(current_pass.encode('utf-8'), stored_hash.encode('utf-8')):
                return False, "Incorrect current password."

            # Hash the new password and update
            new_hash = bcrypt.hashpw(new_pass.encode(
                'utf-8'), bcrypt.gensalt()).decode('utf-8')
            cursor.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (new_hash, user_id)
            )
            conn.commit()
            logger.info(f"Password updated directly for user '{username}'.")
            return True, "Password updated successfully!"

        except sqlite3.Error as e:
            logger.error(f"Direct password update error: {e}")
            return False, f"Database error: {e}"
        finally:
            if conn:
                conn.close()

    def request_password_reset(self, username, email, new_password):
        """Creates a pending password reset request for Admin approval after verifying username AND email."""
        if DATABASE_URL:
            try:
                hashed_pw = bcrypt.hashpw(new_password.encode(
                    'utf-8'), bcrypt.gensalt()).decode('utf-8')
                with get_postgres_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            """
                            SELECT id FROM users
                            WHERE LOWER(username) = %s AND LOWER(email) = %s
                            """,
                            (username.strip().lower(), email.strip().lower()),
                        )
                        if not cursor.fetchone():
                            return False, "Username and registered email do not match any existing account."
                        cursor.execute(
                            "SELECT COALESCE(MAX(id), 0) + 1 FROM password_resets"
                        )
                        request_id = cursor.fetchone()[0]
                        cursor.execute(
                            """
                            INSERT INTO password_resets
                                (id, username, email, desired_password_hash, status)
                            VALUES (%s, %s, %s, %s, 'PENDING')
                            """,
                            (request_id, username.strip(),
                             email.strip().lower(), hashed_pw),
                        )
                    conn.commit()
                return True, "Reset request submitted successfully. Awaiting Admin approval."
            except Exception as e:
                logger.error(f"Reset request database error: {e}")
                return False, "Password reset request could not be submitted. Please try again."
        conn = None
        try:
            conn = sqlite3.connect(self.db_name, timeout=10)
            cursor = conn.cursor()

            cursor.execute(
                "SELECT id FROM users WHERE LOWER(username) = ? AND LOWER(email) = ?",
                (username.strip().lower(), email.strip().lower())
            )
            if not cursor.fetchone():
                return False, "Username and registered email do not match any existing account."

            hashed_pw = bcrypt.hashpw(new_password.encode(
                'utf-8'), bcrypt.gensalt()).decode('utf-8')
            cursor.execute(
                "INSERT INTO reset_requests (email, new_password_hash, status) VALUES (?, ?, 'PENDING')",
                (email.strip().lower(), hashed_pw)
            )
            conn.commit()
            request_id = cursor.lastrowid
            sync_reset_request_to_supabase(
                request_id, email.strip().lower(), hashed_pw, "PENDING")
            logger.info(
                f"Password reset request submitted for user '{username}' with email '{email}'")
            return True, "Reset request submitted successfully. Awaiting Admin approval."
        except sqlite3.Error as e:
            logger.error(f"Reset request database error: {e}")
            return False, f"Database error: {e}"
        finally:
            if conn:
                conn.close()

    def fetch_pending_reset_requests(self):
        """Fetches pending password reset requests from SQLite."""
        if DATABASE_URL:
            try:
                with get_postgres_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            """
                            SELECT r.id, COALESCE(r.username, u.username, r.email), r.email,
                                   CURRENT_TIMESTAMP
                            FROM password_resets r
                            LEFT JOIN users u ON LOWER(r.email) = LOWER(u.email)
                            WHERE UPPER(r.status) = 'PENDING'
                            ORDER BY r.id DESC
                            """
                        )
                        return cursor.fetchall()
            except Exception as e:
                logger.error(f"Error fetching reset requests: {e}")
                return []
        conn = None
        try:
            conn = sqlite3.connect(self.db_name, timeout=10)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT 
                    r.id, 
                    COALESCE(u.username, r.email) AS username, 
                    r.email, 
                    COALESCE(r.created_at, DATETIME('now', 'localtime')) AS created_at
                FROM reset_requests r
                LEFT JOIN users u ON LOWER(r.email) = LOWER(u.email)
                WHERE UPPER(r.status) = 'PENDING'
                ORDER BY r.id DESC
            """)
            return cursor.fetchall()
        except sqlite3.Error as e:
            logger.error(f"Error fetching reset requests: {e}")
            return []
        finally:
            if conn:
                conn.close()

    def process_reset_request(self, request_id, approve=True):
        """Approves or rejects a reset request."""
        if DATABASE_URL:
            try:
                with get_postgres_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "SELECT username, email, desired_password_hash FROM password_resets WHERE id = %s",
                            (request_id,),
                        )
                        req = cursor.fetchone()
                        if not req:
                            return False, "Reset request not found."
                        username, email, new_hash = req
                        if approve:
                            cursor.execute(
                                """
                                UPDATE users
                                SET password_hash = %s, is_locked = 0, failed_attempts = 0
                                WHERE LOWER(email) = %s
                                """,
                                (new_hash, email.lower()),
                            )
                            cursor.execute(
                                "UPDATE password_resets SET status = 'APPROVED' WHERE id = %s",
                                (request_id,),
                            )
                        else:
                            cursor.execute(
                                "UPDATE password_resets SET status = 'REJECTED' WHERE id = %s",
                                (request_id,),
                            )
                    conn.commit()
                return True, f"Password reset for '{username}' successfully {'approved' if approve else 'rejected'}."
            except Exception as e:
                logger.error(f"Error processing reset request: {e}")
                return False, "Password reset request could not be processed. Please try again."
        conn = None
        try:
            conn = sqlite3.connect(self.db_name, timeout=10)
            cursor = conn.cursor()

            if approve:
                cursor.execute(
                    "SELECT email, new_password_hash FROM reset_requests WHERE id = ?", (request_id,))
                req = cursor.fetchone()
                if req:
                    email, new_hash = req
                    cursor.execute(
                        "UPDATE users SET password_hash = ?, is_locked = 0, failed_attempts = 0 WHERE LOWER(email) = ?",
                        (new_hash, email.lower())
                    )
                    cursor.execute(
                        "UPDATE reset_requests SET status = 'APPROVED' WHERE id = ?", (request_id,))
                    sync_reset_request_to_supabase(
                        request_id, email.lower(), new_hash, "APPROVED")
                    cursor.execute(
                        "SELECT id, username, email, password_hash, role, failed_attempts, is_locked FROM users WHERE LOWER(email) = ?", (email.lower(),))
                    user_row = cursor.fetchone()
                    if user_row:
                        sync_user_to_supabase(
                            user_row[0], user_row[1], user_row[2], user_row[3], user_row[4], user_row[5], user_row[6])
            else:
                cursor.execute(
                    "UPDATE reset_requests SET status = 'REJECTED' WHERE id = ?", (request_id,))
                sync_reset_request_to_supabase(
                    request_id, None, None, "REJECTED")

            conn.commit()
            return True, f"Request ID {request_id} successfully {'approved' if approve else 'rejected'}."
        except sqlite3.Error as e:
            logger.error(f"Error processing reset request: {e}")
            return False, f"Database error: {e}"
        finally:
            if conn:
                conn.close()
