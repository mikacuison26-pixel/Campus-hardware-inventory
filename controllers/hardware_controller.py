from logger import logger
import csv
import os
import sqlite3
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

sys.path.append(str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DB_NAME = "hardware_inventory.db"
DATABASE_URL = os.getenv("DATABASE_URL")


def get_postgres_connection():
    if not DATABASE_URL:
        return None
    try:
        return psycopg.connect(DATABASE_URL)
    except Exception as exc:
        logger.warning(f"Postgres connection warning: {exc}")
        return None


def sync_hardware_to_supabase(item_name, category, quantity, unit_price, item_id=None):
    if not DATABASE_URL:
        return

    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                payload = (item_name, category, quantity, unit_price, "In Stock" if quantity >
                           0 and quantity >= 10 else "Low Stock" if quantity > 0 else "Out of Stock")
                if item_id is not None:
                    cur.execute(
                        """
                        INSERT INTO hardware (item_id, item_name, category, quantity, unit_price, status)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (item_id) DO UPDATE SET
                            item_name = EXCLUDED.item_name,
                            category = EXCLUDED.category,
                            quantity = EXCLUDED.quantity,
                            unit_price = EXCLUDED.unit_price,
                            status = EXCLUDED.status
                        """,
                        (item_id, *payload),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO hardware (item_name, category, quantity, unit_price, status)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (item_id) DO NOTHING
                        """,
                        payload,
                    )
    except Exception as exc:
        logger.warning(f"Supabase sync warning for hardware add: {exc}")


class HardwareController:
    def __init__(self, db_name=DB_NAME):
        self.db_name = db_name

    # ---------------- CATALOG & INVENTORY MANAGEMENT ----------------

    def fetch_all_records(self, search_term=""):
        """Fetch all hardware records from Supabase PostgreSQL."""
        if not DATABASE_URL:
            logger.error("DATABASE_URL is not configured.")
            return []

        try:
            with psycopg.connect(DATABASE_URL) as conn:
                with conn.cursor() as cursor:
                    search_pattern = f"%{search_term.strip()}%"

                    query = """
                        SELECT
                            item_id,
                            item_name,
                            category,
                            quantity,
                            unit_price,
                            CASE
                                WHEN quantity <= 0 THEN 'Out of Stock'
                                WHEN quantity < 10 THEN 'Low Stock'
                                ELSE 'In Stock'
                            END AS status
                        FROM hardware
                        WHERE item_name ILIKE %s
                           OR category ILIKE %s
                        ORDER BY item_id ASC
                    """

                    cursor.execute(query, (search_pattern, search_pattern))
                    return cursor.fetchall()

        except Exception as e:
            logger.error(f"PostgreSQL hardware fetch failed: {e}")
            return []

    def get_total_inventory_value(self):
        """Calculates total inventory valuation (quantity * unit_price)."""
        pg_conn = get_postgres_connection()
        if pg_conn is not None:
            try:
                with pg_conn.cursor() as cursor:
                    result = cursor.execute(
                        "SELECT COALESCE(SUM(quantity * unit_price), 0) FROM hardware"
                    ).fetchone()
                    return float(result[0])
            except Exception as e:
                logger.error(f"Error calculating total value: {e}")
                return 0.0
            finally:
                pg_conn.close()
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute("SELECT SUM(quantity * unit_price) FROM hardware")
            result = cursor.fetchone()[0]
            conn.close()
            return result if result is not None else 0.0
        except sqlite3.Error as e:
            logger.error(f"Error calculating total value: {e}")
            return 0.0

    def get_total_stocks(self):
        """Return total hardware stock from Supabase PostgreSQL."""
        if not DATABASE_URL:
            logger.error("DATABASE_URL is not configured.")
            return 0

        try:
            with psycopg.connect(DATABASE_URL) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT COALESCE(SUM(quantity), 0) FROM hardware"
                    )
                    result = cursor.fetchone()
                    return int(result[0] or 0)

        except Exception as e:
            logger.error(f"PostgreSQL total stock fetch failed: {e}")
            return 0

    def get_borrowed_items(self, student_id=None, student_name=None):
        pg_conn = get_postgres_connection()
        if pg_conn is not None:
            try:
                query = """
                    SELECT l.item_id, h.item_name, h.category, l.student_name,
                        l.student_id, COUNT(*) AS quantity,
                        MIN(l.checkout_time) AS checkout_time, l.status
                    FROM asset_loans l JOIN hardware h ON h.item_id = l.item_id
                    WHERE l.status = 'Active'
                """
                params = []
                if student_name:
                    query += " AND l.student_name = %s"
                    params.append(student_name)
                elif student_id:
                    query += " AND l.student_id = %s"
                    params.append(student_id)
                query += " GROUP BY l.item_id, h.item_name, h.category, l.student_name, l.student_id, l.status ORDER BY MAX(l.loan_id) DESC"
                with pg_conn.cursor() as cursor:
                    cursor.execute(query, params)
                    return cursor.fetchall()
            except Exception as e:
                logger.error(f"Error fetching borrowed items: {e}")
                return []
            finally:
                pg_conn.close()
        try:
            with sqlite3.connect(self.db_name) as conn:
                query = """
                    SELECT l.item_id, h.item_name, h.category, l.student_name,
                        l.student_id, COUNT(*) AS quantity,
                        MIN(l.checkout_time) AS checkout_time, l.status
                    FROM asset_loans l JOIN hardware h ON h.item_id = l.item_id
                    WHERE l.status = 'Active'
                """
                params = ()
                if student_name:
                    query += " AND l.student_name = ?"
                    params = (student_name,)
                elif student_id:
                    query += " AND l.student_id = ?"
                    params = (student_id,)
                query += " GROUP BY l.item_id, h.item_name, h.category, l.student_name, l.student_id, l.status ORDER BY MAX(l.loan_id) DESC"
                return conn.execute(query, params).fetchall()
        except sqlite3.Error as e:
            logger.error(f"Error fetching borrowed items: {e}")
            return []

    def get_history_records(self, student_name=None):
        pg_conn = get_postgres_connection()
        if pg_conn is not None:
            try:
                query = """
                    SELECT h.item_name, h.category,
                        l.student_name, l.student_id,
                        1 AS quantity, l.status,
                        l.created_at, l.checkout_time, l.return_time
                    FROM asset_loans l
                    JOIN hardware h ON h.item_id = l.item_id
                    WHERE TRUE
                """
                params = []
                if student_name:
                    query += " AND l.student_name = %s"
                    params.append(student_name)
                query += " ORDER BY l.loan_id DESC"
                with pg_conn.cursor() as cursor:
                    cursor.execute(query, params)
                    return cursor.fetchall()
            except Exception as e:
                logger.error(f"Error fetching loan history: {e}")
                return []
            finally:
                pg_conn.close()
        try:
            with sqlite3.connect(self.db_name) as conn:
                query = """
                    SELECT h.item_name, h.category,
                        l.student_name, l.student_id,
                        1 AS quantity, l.status,
                        l.created_at, l.checkout_time, l.return_time
                    FROM asset_loans l
                    JOIN hardware h ON h.item_id = l.item_id
                    WHERE 1 = 1
                """
                params = []
                if student_name:
                    query += " AND l.student_name = ?"
                    params.append(student_name)
                query += " ORDER BY l.loan_id DESC"
                return conn.execute(query, params).fetchall()
        except sqlite3.Error as e:
            logger.error(f"Error fetching loan history: {e}")
            return []

    def get_pending_borrow_requests(self):
        pg_conn = get_postgres_connection()
        if pg_conn is not None:
            try:
                with pg_conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT b.request_id, h.item_name, b.student_name, b.student_id,
                               b.quantity, b.created_at
                        FROM borrow_requests b JOIN hardware h ON h.item_id = b.item_id
                        WHERE b.status = 'Pending' ORDER BY b.request_id DESC
                    """)
                    return cursor.fetchall()
            except Exception as e:
                logger.error(f"Error fetching borrow requests: {e}")
                return []
            finally:
                pg_conn.close()
        try:
            with sqlite3.connect(self.db_name) as conn:
                return conn.execute("""
                    SELECT b.request_id, h.item_name, b.student_name, b.student_id, b.quantity, b.created_at
                    FROM borrow_requests b JOIN hardware h ON h.item_id = b.item_id
                    WHERE b.status = 'Pending' ORDER BY b.request_id DESC
                """).fetchall()
        except sqlite3.Error as e:
            logger.error(f"Error fetching borrow requests: {e}")
            return []

    def get_pending_return_requests(self):
        pg_conn = get_postgres_connection()
        if pg_conn is not None:
            try:
                with pg_conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT MIN(r.request_id), h.item_name, l.student_name,
                               r.student_id, COUNT(*) AS quantity, MIN(r.created_at)
                        FROM return_requests r
                        JOIN asset_loans l ON l.loan_id = r.loan_id
                        JOIN hardware h ON h.item_id = l.item_id
                        WHERE r.status = 'Pending'
                        GROUP BY l.item_id, h.item_name, l.student_name, r.student_id
                        ORDER BY MIN(r.request_id) DESC
                    """)
                    return cursor.fetchall()
            except Exception as e:
                logger.error(f"Error fetching return requests: {e}")
                return []
            finally:
                pg_conn.close()
        try:
            with sqlite3.connect(self.db_name) as conn:
                return conn.execute("""
                    SELECT MIN(r.request_id), h.item_name, l.student_name,
                        r.student_id, COUNT(*) AS quantity, MIN(r.created_at)
                    FROM return_requests r
                    JOIN asset_loans l ON l.loan_id = r.loan_id
                    JOIN hardware h ON h.item_id = l.item_id
                    WHERE r.status = 'Pending'
                    GROUP BY l.item_id, l.student_name, r.student_id
                    ORDER BY MIN(r.request_id) DESC
                """).fetchall()
        except sqlite3.Error as e:
            logger.error(f"Error fetching return requests: {e}")
            return []

    def request_borrow(self, item_id, student_id, quantity, student_name=None):
        try:
            student_id = student_id.strip()
            student_name = (student_name or student_id).strip()
            if not student_id:
                return False, "Student ID is required."
            quantity = int(quantity)
            if quantity <= 0:
                return False, "Borrow quantity must be greater than zero."

            pg_conn = get_postgres_connection()
            if pg_conn is not None:
                try:
                    with pg_conn.cursor() as cursor:
                        cursor.execute(
                            "SELECT quantity FROM hardware WHERE item_id = %s FOR UPDATE",
                            (item_id,),
                        )
                        item = cursor.fetchone()
                        if not item:
                            return False, "Item not found."
                        cursor.execute(
                            """
                            SELECT COALESCE(SUM(quantity), 0)
                            FROM borrow_requests
                            WHERE item_id = %s AND status = 'Pending'
                            """,
                            (item_id,),
                        )
                        pending = cursor.fetchone()[0]
                        if quantity + pending > item[0]:
                            return False, "Requested quantity exceeds available stock."
                        cursor.execute(
                            "SELECT COALESCE(MAX(request_id), 0) + 1 FROM borrow_requests"
                        )
                        request_id = cursor.fetchone()[0]
                        cursor.execute(
                            """
                            INSERT INTO borrow_requests
                                (request_id, item_id, student_id, student_name, quantity, status)
                            VALUES (%s, %s, %s, %s, %s, 'Pending')
                            """,
                            (request_id, item_id, student_id,
                             student_name, quantity),
                        )
                    pg_conn.commit()
                    return True, "Borrow request submitted for approval."
                finally:
                    pg_conn.close()

            with sqlite3.connect(self.db_name) as conn:
                item = conn.execute(
                    "SELECT quantity FROM hardware WHERE item_id = ?", (item_id,)).fetchone()
                if not item:
                    return False, "Item not found."
                pending = conn.execute("""
                    SELECT COALESCE(SUM(quantity), 0) FROM borrow_requests
                    WHERE item_id = ? AND status = 'Pending'
                """, (item_id,)).fetchone()[0]
                if quantity + pending > item[0]:
                    return False, "Requested quantity exceeds available stock."
                conn.execute("""
                    INSERT INTO borrow_requests
                        (item_id, student_id, student_name, quantity, created_at)
                    VALUES (?, ?, ?, ?, datetime('now', '+8 hours'))
                """, (item_id, student_id, student_name, quantity))
            return True, "Borrow request submitted for approval."
        except (ValueError, sqlite3.Error, psycopg.Error) as e:
            logger.error(f"Borrow request failed: {e}")
            return False, "Borrow request could not be submitted. Please try again."

    def approve_borrow_request(self, request_id, approve=True):
        pg_conn = get_postgres_connection()
        if pg_conn is not None:
            try:
                with pg_conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT item_id, student_id, student_name, quantity, status, created_at
                        FROM borrow_requests
                        WHERE request_id = %s
                        FOR UPDATE
                        """,
                        (request_id,),
                    )
                    row = cursor.fetchone()
                    if not row:
                        return False, "Borrow request not found."
                    item_id, student_id, student_name, quantity, status, request_created_at = row
                    if status != "Pending":
                        return False, "Borrow request has already been processed."
                    if approve:
                        cursor.execute(
                            "SELECT quantity FROM hardware WHERE item_id = %s FOR UPDATE", (item_id,))
                        stock = cursor.fetchone()
                        if not stock or stock[0] < quantity:
                            return False, "Cannot approve: insufficient stock."
                        cursor.execute(
                            """
                            UPDATE hardware
                            SET quantity = quantity - %s,
                                status = CASE WHEN quantity - %s <= 0 THEN 'Out of Stock'
                                    WHEN quantity - %s < 10 THEN 'Low Stock' ELSE 'In Stock' END
                            WHERE item_id = %s
                            """,
                            (quantity, quantity, quantity, item_id),
                        )
                        cursor.execute(
                            "SELECT COALESCE(MAX(loan_id), 0) FROM asset_loans"
                        )
                        next_loan_id = cursor.fetchone()[0] + 1
                        cursor.executemany(
                            """
                            INSERT INTO asset_loans
                                (loan_id, item_id, student_id, student_name,
                                 created_at, checkout_time, return_time, status)
                            VALUES (
                                %s, %s, %s, %s, %s,
                                CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Manila',
                                NULL, 'Active'
                            )
                            """,
                            [
                                (next_loan_id + offset, item_id,
                                 student_id, student_name, request_created_at)
                                for offset in range(quantity)
                            ],
                        )
                    cursor.execute(
                        "UPDATE borrow_requests SET status = %s WHERE request_id = %s",
                        ('Approved' if approve else 'Rejected', request_id),
                    )
                pg_conn.commit()
                return True, f"Borrow request {'approved' if approve else 'rejected'}."
            except Exception as e:
                logger.error(f"Borrow approval failed: {e}")
                return False, f"Borrow approval failed: {e}"
            finally:
                pg_conn.close()
        try:
            with sqlite3.connect(self.db_name) as conn:
                row = conn.execute(
                    "SELECT item_id, student_id, student_name, quantity, status, created_at FROM borrow_requests WHERE request_id = ?", (request_id,)).fetchone()
                if not row:
                    return False, "Borrow request not found."
                item_id, student_id, student_name, quantity, status, request_created_at = row
                if status != "Pending":
                    return False, "Borrow request has already been processed."
                if approve:
                    stock = conn.execute(
                        "SELECT quantity FROM hardware WHERE item_id = ?", (item_id,)).fetchone()
                    if not stock or stock[0] < quantity:
                        return False, "Cannot approve: insufficient stock."
                    conn.execute("UPDATE hardware SET quantity = quantity - ?, status = CASE WHEN quantity - ? <= 0 THEN 'Out of Stock' WHEN quantity - ? < 10 THEN 'Low Stock' ELSE 'In Stock' END WHERE item_id = ?",
                                 (quantity, quantity, quantity, item_id))
                    for _ in range(quantity):
                        conn.execute(
                            """
                            INSERT INTO asset_loans
                                (item_id, student_id, student_name, created_at,
                                 checkout_time, return_time, status)
                            VALUES (?, ?, ?, ?, datetime('now', '+8 hours'), NULL, 'Active')
                            """,
                            (item_id, student_id, student_name, request_created_at),
                        )
                conn.execute("UPDATE borrow_requests SET status = ? WHERE request_id = ?",
                             ('Approved' if approve else 'Rejected', request_id))
            return True, f"Borrow request {'approved' if approve else 'rejected'}."
        except sqlite3.Error as e:
            return False, f"Borrow approval failed: {e}"

    def request_return(self, loan_id, student_id, student_name):
        try:
            with sqlite3.connect(self.db_name) as conn:
                loan = conn.execute(
                    "SELECT status, student_id, student_name FROM asset_loans WHERE loan_id = ?", (loan_id,)).fetchone()
                if not loan or loan[0] != 'Active' or loan[2] != student_name:
                    return False, "Active borrowed item not found."
                loan_student_id = (loan[1] or "").strip()
                if not loan_student_id or loan_student_id.upper() == "EMPTY":
                    return False, "Student ID is missing from this loan. Please contact an administrator."
                existing = conn.execute(
                    "SELECT 1 FROM return_requests WHERE loan_id = ? AND status = 'Pending'", (loan_id,)).fetchone()
                if existing:
                    return False, "A return request is already pending."
                conn.execute(
                    "INSERT INTO return_requests (loan_id, student_id) VALUES (?, ?)",
                    (loan_id, loan_student_id))
            return True, "Return request submitted for approval."
        except sqlite3.Error as e:
            return False, f"Return request failed: {e}"

    def request_return_quantity(self, item_id, student_id, student_name, quantity):
        try:
            quantity = int(quantity)
            if quantity <= 0:
                return False, "Return quantity must be greater than zero."

            pg_conn = get_postgres_connection()
            if pg_conn is not None:
                try:
                    with pg_conn.cursor() as cursor:
                        cursor.execute(
                            """
                            SELECT l.loan_id, l.student_id
                            FROM asset_loans l
                            WHERE l.item_id = %s AND l.student_name = %s
                              AND l.status = 'Active'
                            ORDER BY l.loan_id ASC
                            """,
                            (item_id, student_name),
                        )
                        active_loans = cursor.fetchall()
                        if len(active_loans) < quantity:
                            return False, f"You only have {len(active_loans)} active item(s) to return."
                        cursor.execute(
                            """
                            SELECT l.loan_id
                            FROM return_requests r
                            JOIN asset_loans l ON l.loan_id = r.loan_id
                            WHERE r.status = 'Pending'
                              AND l.item_id = %s AND l.student_name = %s
                            """,
                            (item_id, student_name),
                        )
                        pending_loan_ids = {row[0]
                                            for row in cursor.fetchall()}
                        missing_quantity = quantity - len(pending_loan_ids)
                        if missing_quantity <= 0:
                            return True, "A return request for that quantity is already pending admin approval."
                        loans = [
                            loan for loan in active_loans
                            if loan[0] not in pending_loan_ids
                        ][:missing_quantity]
                        if any(not (loan[1] or "").strip() or loan[1].strip().upper() == "EMPTY" for loan in loans):
                            return False, "Student ID is missing from one or more loans. Please contact an administrator."
                        cursor.execute(
                            "SELECT COALESCE(MAX(request_id), 0) FROM return_requests"
                        )
                        next_request_id = cursor.fetchone()[0] + 1
                        cursor.executemany(
                            """
                            INSERT INTO return_requests
                                (request_id, loan_id, student_id, status)
                            VALUES (%s, %s, %s, 'Pending')
                            """,
                            [
                                (next_request_id + offset, loan[0], loan[1].strip())
                                for offset, loan in enumerate(loans)
                            ],
                        )
                    pg_conn.commit()
                    return True, f"Return request submitted for {quantity} item(s)."
                finally:
                    pg_conn.close()

            with sqlite3.connect(self.db_name) as conn:
                loans = conn.execute("""
                    SELECT l.loan_id, l.student_id
                    FROM asset_loans l
                    WHERE l.item_id = ? AND l.student_name = ? AND l.status = 'Active'
                    ORDER BY l.loan_id ASC
                """, (item_id, student_name)).fetchall()
                if len(loans) < quantity:
                    return False, f"You only have {len(loans)} active item(s) to return."
                pending_loan_ids = {
                    row[0] for row in conn.execute(
                        """
                        SELECT r.loan_id
                        FROM return_requests r
                        JOIN asset_loans l ON l.loan_id = r.loan_id
                        WHERE r.status = 'Pending'
                          AND l.item_id = ? AND l.student_name = ?
                        """,
                        (item_id, student_name),
                    ).fetchall()
                }
                missing_quantity = quantity - len(pending_loan_ids)
                if missing_quantity <= 0:
                    return True, "A return request for that quantity is already pending admin approval."
                loans = [
                    loan for loan in loans if loan[0] not in pending_loan_ids
                ][:missing_quantity]
                if any(not (loan[1] or "").strip() or loan[1].strip().upper() == "EMPTY" for loan in loans):
                    return False, "Student ID is missing from one or more loans. Please contact an administrator."
                conn.executemany(
                    "INSERT INTO return_requests (loan_id, student_id) VALUES (?, ?)",
                    [(loan[0], loan[1].strip()) for loan in loans],
                )
            return True, f"Return request submitted for {quantity} item(s)."
        except (ValueError, sqlite3.Error) as e:
            return False, f"Return request failed: {e}"

    def approve_return_request(self, request_id, approve=True):
        pg_conn = get_postgres_connection()
        if pg_conn is not None:
            try:
                with pg_conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT r.loan_id, r.status, l.item_id, l.student_name, r.student_id
                        FROM return_requests r JOIN asset_loans l ON l.loan_id = r.loan_id
                        WHERE r.request_id = %s FOR UPDATE
                        """,
                        (request_id,),
                    )
                    row = cursor.fetchone()
                    if not row or row[1] != 'Pending':
                        return False, "Return request is unavailable."
                    item_id, student_name, student_id = row[2], row[3], row[4]
                    cursor.execute(
                        """
                        SELECT r.request_id, r.loan_id
                        FROM return_requests r JOIN asset_loans l ON l.loan_id = r.loan_id
                        WHERE r.status = 'Pending' AND l.item_id = %s
                          AND l.student_name = %s AND r.student_id = %s
                        """,
                        (item_id, student_name, student_id),
                    )
                    request_rows = cursor.fetchall()
                    loan_ids = [request[1] for request in request_rows]
                    if approve:
                        cursor.execute(
                            "SELECT COUNT(*) FROM asset_loans WHERE loan_id = ANY(%s) AND status = 'Active'",
                            (loan_ids,),
                        )
                        if cursor.fetchone()[0] != len(loan_ids):
                            return False, "Borrowed item is unavailable."
                        cursor.execute(
                            "UPDATE asset_loans SET status = 'Returned', return_time = (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Manila') WHERE loan_id = ANY(%s)",
                            (loan_ids,),
                        )
                        cursor.execute(
                            """
                            UPDATE hardware
                            SET quantity = quantity + %s,
                                status = CASE WHEN quantity + %s < 10 THEN 'Low Stock' ELSE 'In Stock' END
                            WHERE item_id = %s
                            """,
                            (len(loan_ids), len(loan_ids), item_id),
                        )
                    cursor.execute(
                        "UPDATE return_requests SET status = %s WHERE request_id = ANY(%s)",
                        ('Approved' if approve else 'Rejected',
                         [request[0] for request in request_rows]),
                    )
                pg_conn.commit()
                return True, f"Return request {'approved' if approve else 'rejected'} for {len(request_rows)} item(s)."
            except Exception as e:
                logger.error(f"Return approval failed: {e}")
                return False, f"Return approval failed: {e}"
            finally:
                pg_conn.close()
        try:
            with sqlite3.connect(self.db_name) as conn:
                row = conn.execute(
                    """
                    SELECT r.loan_id, r.status, l.item_id, l.student_name, r.student_id
                    FROM return_requests r JOIN asset_loans l ON l.loan_id = r.loan_id
                    WHERE r.request_id = ?
                    """, (request_id,)).fetchone()
                if not row or row[1] != 'Pending':
                    return False, "Return request is unavailable."
                item_id, student_name, student_id = row[2], row[3], row[4]
                request_rows = conn.execute("""
                    SELECT r.request_id, r.loan_id
                    FROM return_requests r JOIN asset_loans l ON l.loan_id = r.loan_id
                    WHERE r.status = 'Pending' AND l.item_id = ?
                        AND l.student_name = ? AND r.student_id = ?
                """, (item_id, student_name, student_id)).fetchall()
                loan_ids = [request[1] for request in request_rows]
                if approve:
                    active_count = conn.execute(
                        "SELECT COUNT(*) FROM asset_loans WHERE loan_id IN ({}) AND status = 'Active'".format(
                            ','.join('?' for _ in loan_ids)), loan_ids).fetchone()[0] if loan_ids else 0
                    if active_count != len(loan_ids):
                        return False, "Borrowed item is unavailable."
                    conn.execute(
                        "UPDATE asset_loans SET status = 'Returned', return_time = datetime('now', '+8 hours') WHERE loan_id IN ({})".format(
                            ','.join('?' for _ in loan_ids)), loan_ids)
                    conn.execute(
                        "UPDATE hardware SET quantity = quantity + ?, status = CASE WHEN quantity + ? <= 0 THEN 'Out of Stock' WHEN quantity + ? < 10 THEN 'Low Stock' ELSE 'In Stock' END WHERE item_id = ?",
                        (len(loan_ids), len(loan_ids), len(loan_ids), item_id))
                conn.execute("UPDATE return_requests SET status = ? WHERE request_id = ?",
                             ('Approved' if approve else 'Rejected', request_id))
                if len(request_rows) > 1:
                    conn.executemany(
                        "UPDATE return_requests SET status = ? WHERE request_id = ?",
                        [('Approved' if approve else 'Rejected', request[0])
                         for request in request_rows if request[0] != request_id],
                    )
            return True, f"Return request {'approved' if approve else 'rejected'} for {len(request_rows)} item(s)."
        except sqlite3.Error as e:
            return False, f"Return approval failed: {e}"

    def add_hardware(self, name, category, quantity, unit_price):
        """Adds a new item to the inventory and computes its status dynamically."""
        try:
            qty = int(quantity)
            price = float(unit_price)

            if qty <= 0:
                status = "Out of Stock"
            elif qty < 10:
                status = "Low Stock"
            else:
                status = "In Stock"

            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO hardware (item_name, category, quantity, unit_price, status)
                VALUES (?, ?, ?, ?, ?)
            """, (name, category, qty, price, status))
            conn.commit()
            new_item_id = cursor.lastrowid
            conn.close()

            sync_hardware_to_supabase(name, category, qty, price, new_item_id)

            logger.info(
                f"HARDWARE ADDED: '{name}' (Qty: {qty}, Price: {price})")
            return True, "Hardware item added successfully."
        except ValueError:
            return False, "Quantity must be an integer and price must be a number."
        except sqlite3.Error as e:
            logger.error(f"Error adding hardware: {e}")
            return False, f"Database error: {e}"

    def update_hardware(self, item_id, new_quantity, new_price):
        """Updates quantity and unit price for an item and recalculates status."""
        try:
            qty = int(new_quantity)
            price = float(new_price)

            if qty <= 0:
                status = "Out of Stock"
            elif qty < 10:
                status = "Low Stock"
            else:
                status = "In Stock"

            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE hardware 
                SET quantity = ?, unit_price = ?, status = ?
                WHERE item_id = ?
            """, (qty, price, status, item_id))
            conn.commit()
            cursor.execute(
                "SELECT item_name, category FROM hardware WHERE item_id = ?", (item_id,))
            item_row = cursor.fetchone()
            conn.close()
            if item_row:
                sync_hardware_to_supabase(
                    item_row[0], item_row[1], qty, price, item_id)
            logger.info(
                f"HARDWARE UPDATED: Item ID {item_id} -> Qty: {qty}, Price: {price}")
            return True, "Item updated successfully."
        except ValueError:
            return False, "Quantity must be an integer and price must be a number."
        except sqlite3.Error as e:
            logger.error(f"Error updating hardware: {e}")
            return False, f"Database error: {e}"

    def delete_hardware(self, item_id):
        """Deletes an item from the hardware table."""
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT item_name, category FROM hardware WHERE item_id = ?", (item_id,))
            item_row = cursor.fetchone()
            cursor.execute(
                "DELETE FROM hardware WHERE item_id = ?", (item_id,))
            conn.commit()
            conn.close()
            if item_row:
                try:
                    with psycopg.connect(DATABASE_URL) as pg:
                        with pg.cursor() as cur:
                            cur.execute(
                                "DELETE FROM hardware WHERE item_id = %s", (item_id,))
                except Exception as exc:
                    logger.warning(f"Supabase hardware delete warning: {exc}")
            logger.info(f"HARDWARE DELETED: Item ID {item_id}")
            return True, "Item deleted successfully."
        except sqlite3.Error as e:
            logger.error(f"Error deleting hardware: {e}")
            return False, f"Database error: {e}"

    # ---------------- MODULE 1: CHECK-IN / CHECK-OUT ----------------

    def checkout_item(self, item_id, student_id):
        """Decrements quantity by 1, updates status, and logs active loan."""
        if not student_id.strip():
            return False, "Student ID cannot be empty."

        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()

            cursor.execute(
                "SELECT quantity FROM hardware WHERE item_id = ?", (item_id,))
            row = cursor.fetchone()

            if not row:
                conn.close()
                return False, "Item not found."

            current_qty = int(row[0])
            if current_qty <= 0:
                conn.close()
                return False, "Item is Out of Stock and cannot be checked out."

            new_qty = current_qty - 1
            new_status = "Out of Stock" if new_qty == 0 else (
                "Low Stock" if new_qty < 10 else "In Stock")

            cursor.execute("""
                UPDATE hardware SET quantity = ?, status = ? WHERE item_id = ?
            """, (new_qty, new_status, item_id))

            cursor.execute("""
                INSERT INTO asset_loans
                    (item_id, student_id, created_at, checkout_time, return_time, status)
                VALUES (?, ?, datetime('now', '+8 hours'), datetime('now', '+8 hours'), NULL, 'Active')
            """, (item_id, student_id.strip()))

            conn.commit()
            conn.close()
            try:
                item_name = conn.execute(
                    "SELECT item_name FROM hardware WHERE item_id = ?", (item_id,)).fetchone()
            except Exception:
                item_name = None
            try:
                if DATABASE_URL:
                    with psycopg.connect(DATABASE_URL) as pg:
                        with pg.cursor() as cur:
                            cur.execute(
                                """
                                INSERT INTO asset_loans
                                    (item_id, student_id, created_at, checkout_time, return_time, status)
                                VALUES (%s, %s,
                                    CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Manila',
                                    CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Manila',
                                    NULL, 'Active')
                                ON CONFLICT DO NOTHING
                                """,
                                (item_id, student_id.strip()),
                            )
                            cur.execute(
                                "UPDATE hardware SET quantity = %s, status = %s WHERE item_id = %s",
                                (new_qty, new_status, item_id),
                            )
            except Exception as exc:
                logger.warning(f"Supabase checkout sync warning: {exc}")
            logger.info(
                f"CHECKOUT EVENT: Item ID {item_id} issued to Student '{student_id}'. New Qty: {new_qty}")
            return True, "Item checked out successfully."
        except sqlite3.Error as e:
            logger.error(f"Error during checkout: {e}")
            return False, f"Database error: {e}"

    def return_item(self, item_id):
        """Increments quantity by 1, updates status, and closes the active loan."""
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()

            cursor.execute(
                "SELECT quantity FROM hardware WHERE item_id = ?", (item_id,))
            row = cursor.fetchone()

            if not row:
                conn.close()
                return False, "Item not found."

            new_qty = int(row[0]) + 1
            new_status = "Out of Stock" if new_qty == 0 else (
                "Low Stock" if new_qty < 10 else "In Stock")

            cursor.execute("""
                UPDATE hardware SET quantity = ?, status = ? WHERE item_id = ?
            """, (new_qty, new_status, item_id))

            cursor.execute("""
                UPDATE asset_loans 
                SET status = 'Returned', return_time = datetime('now', '+8 hours')
                WHERE loan_id = (
                    SELECT loan_id FROM asset_loans 
                    WHERE item_id = ? AND status = 'Active' 
                    ORDER BY loan_id DESC LIMIT 1
                )
            """, (item_id,))

            conn.commit()
            conn.close()
            try:
                if DATABASE_URL:
                    with psycopg.connect(DATABASE_URL) as pg:
                        with pg.cursor() as cur:
                            cur.execute(
                                "UPDATE hardware SET quantity = %s, status = %s WHERE item_id = %s",
                                (new_qty, new_status, item_id),
                            )
                            cur.execute(
                                "UPDATE asset_loans SET status = 'Returned', return_time = (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Manila') WHERE loan_id = (SELECT loan_id FROM asset_loans WHERE item_id = %s AND status = 'Active' ORDER BY loan_id DESC LIMIT 1)",
                                (item_id,),
                            )
            except Exception as exc:
                logger.warning(f"Supabase return sync warning: {exc}")
            logger.info(
                f"RETURN EVENT: Item ID {item_id} returned. New Qty: {new_qty}")
            return True, "Item returned successfully."
        except sqlite3.Error as e:
            logger.error(f"Error during return: {e}")
            return False, f"Database error: {e}"

    def fetch_catalog_with_availability(self):
        """
        Fetches catalog items and computes Total Qty, Active Reserved Qty, and Available Qty.
        Available Qty = Total Qty - (Approved or Pending Reservations)
        """
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()

            query = """
                SELECT 
                    h.item_id,
                    h.item_name,
                    h.category,
                    h.quantity AS total_qty,
                    COALESCE(SUM(CASE WHEN r.status IN ('Approved', 'Pending') THEN 1 ELSE 0 END), 0) AS reserved_qty,
                    (h.quantity - COALESCE(SUM(CASE WHEN r.status IN ('Approved', 'Pending') THEN 1 ELSE 0 END), 0)) AS available_qty,
                    h.unit_price
                FROM hardware h
                LEFT JOIN reservations r ON h.item_id = r.item_id
                GROUP BY h.item_id
            """
            cursor.execute(query)
            records = cursor.fetchall()
            conn.close()
            return records
        except sqlite3.Error as e:
            logger.error(f"Error fetching catalog with availability: {e}")
            return []

    # ---------------- MODULE 2: TIME-SLOT RESERVATIONS ----------------

    def add_reservation(self, item_id, student_id, start_time, end_time):
        """
        Creates a new pending reservation in the database with fallback 
        connection handling.
        """
        conn = None

        # 1. Try retrieving the active connection attribute from self
        for attr in ['db', 'db_conn', 'conn', 'database']:
            obj = getattr(self, attr, None)
            if obj is not None:
                if hasattr(obj, 'cursor'):
                    conn = obj
                    break
                elif hasattr(obj, 'conn') and obj.conn is not None:
                    conn = obj.conn
                    break
                elif callable(obj):
                    try:
                        conn = obj()
                        break
                    except Exception:
                        pass

        # 2. Fallback: If self attributes are None, use the same database as the app
        if conn is None:
            try:
                conn = sqlite3.connect(self.db_name)
            except Exception as conn_err:
                return False, f"Could not establish database connection: {conn_err}"

        # 3. Execute INSERT query
        try:
            cursor = conn.cursor()
            query = """
                INSERT INTO reservations (item_id, student_id, start_time, end_time, status)
                VALUES (?, ?, ?, ?, 'Pending');
            """
            cursor.execute(query, (item_id, student_id, start_time, end_time))
            conn.commit()
            reservation_id = cursor.lastrowid

            # Close local connection if created dynamically
            if hasattr(conn, 'close') and not hasattr(self, 'db'):
                conn.close()

            try:
                if DATABASE_URL:
                    with psycopg.connect(DATABASE_URL) as pg:
                        with pg.cursor() as cur:
                            cur.execute(
                                """
                                INSERT INTO reservations (reservation_id, item_id, student_id, start_time, end_time, status, notified)
                                VALUES (%s, %s, %s, %s, %s, 'Pending', 0)
                                ON CONFLICT (reservation_id) DO UPDATE SET
                                    item_id = EXCLUDED.item_id,
                                    student_id = EXCLUDED.student_id,
                                    start_time = EXCLUDED.start_time,
                                    end_time = EXCLUDED.end_time,
                                    status = EXCLUDED.status,
                                    notified = EXCLUDED.notified
                                """,
                                (reservation_id, item_id,
                                 student_id, start_time, end_time),
                            )
            except Exception as exc:
                logger.warning(f"Supabase reservation sync warning: {exc}")

            return True, "Reservation request submitted for approval!"

        except Exception as e:
            print(f"Database insertion error: {e}")
            return False, f"Database error: {str(e)}"

    def fetch_all_reservations(self):
        """Fetches active reservation requests joined with item details."""
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT r.reservation_id, h.item_name, r.student_id, r.start_time, r.end_time, 
                       COALESCE(r.status, 'Pending') AS status
                FROM reservations r
                JOIN hardware h ON r.item_id = h.item_id
                WHERE LOWER(COALESCE(r.status, 'pending')) NOT IN ('rejected', 'completed', 'cancelled')
                ORDER BY r.start_time ASC
            """)
            records = cursor.fetchall()
            conn.close()
            return records
        except sqlite3.Error as e:
            logger.error(f"Error fetching reservations: {e}")
            return []

    def update_reservation_status(self, reservation_id, status):
        """
        Updates status ('Approved' or 'Rejected') for admin review.
        Decrements hardware stock on approval and resets 'notified' flag to 0.
        """
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()

            # 1. Fetch current status and item_id for this reservation
            cursor.execute("""
                SELECT item_id, status 
                FROM reservations 
                WHERE reservation_id = ?
            """, (reservation_id,))
            res = cursor.fetchone()

            if not res:
                conn.close()
                return False, f"Reservation ID {reservation_id} not found."

            item_id, current_status = res

            # Normalize status strings for comparison
            target_status = status.strip().capitalize()
            prev_status = (current_status or "").strip().capitalize()

            # 2. Handle stock deduction if transitioning to 'Approved'
            if target_status == "Approved" and prev_status != "Approved":
                # Check available quantity
                cursor.execute(
                    "SELECT quantity FROM hardware WHERE item_id = ?", (item_id,))
                item = cursor.fetchone()

                if not item or item[0] <= 0:
                    conn.close()
                    return False, "Cannot approve reservation: Item is out of stock."

                # Decrement hardware stock quantity by 1
                cursor.execute("""
                    UPDATE hardware 
                    SET quantity = quantity - 1 
                    WHERE item_id = ? AND quantity > 0
                """, (item_id,))

            # 3. Handle stock restoration if changing from 'Approved' to 'Rejected'
            elif target_status == "Rejected" and prev_status == "Approved":
                cursor.execute("""
                    UPDATE hardware 
                    SET quantity = quantity + 1 
                    WHERE item_id = ?
                """, (item_id,))

            # 4. Update reservation status and reset notification flag
            cursor.execute("""
                UPDATE reservations 
                SET status = ?, notified = 0 
                WHERE reservation_id = ?
            """, (target_status, reservation_id))

            conn.commit()
            conn.close()

            try:
                if DATABASE_URL:
                    with psycopg.connect(DATABASE_URL) as pg:
                        with pg.cursor() as cur:
                            cur.execute(
                                "UPDATE reservations SET status = %s, notified = 0 WHERE reservation_id = %s",
                                (target_status, reservation_id),
                            )
            except Exception as exc:
                logger.warning(
                    f"Supabase reservation status sync warning: {exc}")

            logger.info(
                f"RESERVATION STATUS UPDATED: ID {reservation_id} set to '{target_status}'."
            )
            return True, f"Reservation status updated to '{target_status}'."

        except sqlite3.Error as e:
            logger.error(f"Error updating reservation status: {e}")
            return False, f"Database error: {e}"

    def check_user_notifications(self, student_id):
        """
        Fetches unread notifications for a user upon login and marks them as read (notified = 1).
        """
        notifications = []
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT r.reservation_id, h.item_name, r.status 
                FROM reservations r
                JOIN hardware h ON r.item_id = h.item_id
                WHERE r.student_id = ? AND r.status IN ('Approved', 'Rejected') AND r.notified = 0
            """, (student_id.strip(),))

            unnotified = cursor.fetchall()

            for res_id, item_name, status in unnotified:
                if status == 'Approved':
                    notifications.append(
                        f"✅ Reservation #{res_id} for '{item_name}' was APPROVED!")
                elif status == 'Rejected':
                    notifications.append(
                        f"❌ Reservation #{res_id} for '{item_name}' was REJECTED.")

                cursor.execute("""
                    UPDATE reservations 
                    SET notified = 1 
                    WHERE reservation_id = ?
                """, (res_id,))

            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            logger.error(f"Error retrieving user notifications: {e}")

        return notifications

    def delete_reservation(self, reservation_id):
        """Deletes a reservation entry from the database table."""
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()

            cursor.execute("""
                DELETE FROM reservations 
                WHERE reservation_id = ?
            """, (reservation_id,))

            conn.commit()
            conn.close()
            logger.info(
                f"RESERVATION DELETED: ID {reservation_id} removed from database."
            )
            return True, f"Reservation ID {reservation_id} deleted successfully."
        except sqlite3.Error as e:
            logger.error(f"Error deleting reservation: {e}")
            return False, f"Database error: {e}"

    # ---------------- MODULE 3: LOGBOOK EXPORT ----------------

    def export_to_csv(self, filename="inventory_report.csv"):
        """Exports complete active loan usage history to CSV file."""
        try:
            conn = sqlite3.connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT l.loan_id, h.item_name, l.student_id, l.checkout_time, l.return_time, l.status
                FROM asset_loans l
                JOIN hardware h ON l.item_id = h.item_id
                ORDER BY l.loan_id DESC
            """)
            loans = cursor.fetchall()
            conn.close()

            with open(filename, mode="w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(["Loan ID", "Item Name", "Student ID",
                                "Checkout Time", "Return Time", "Status"])
                for row in loans:
                    writer.writerow(row)

            logger.info(
                f"REPORT GENERATION: Logbook exported to '{filename}'.")
            return True, f"Report exported successfully to {filename}"
        except Exception as e:
            logger.error(f"Export Error: {e}")
            return False, f"Export failed: {str(e)}"
