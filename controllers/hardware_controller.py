from logger import logger
from models.database import db_connect, log_activity
import csv
import sqlite3
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))


DB_NAME = "hardware_inventory.db"


class HardwareController:
    def __init__(self, db_name=DB_NAME):
        self.db_name = db_name

    # ---------------- CATALOG & INVENTORY MANAGEMENT ----------------

    def fetch_all_records(self, search_term=""):
        """Fetches all items from the hardware table."""
        try:
            conn = db_connect(self.db_name)
            cursor = conn.cursor()
            query = """
                SELECT item_id, item_name, category, quantity, unit_price,
                    CASE
                        WHEN quantity <= 0 THEN 'Out of Stock'
                        WHEN quantity < 10 THEN 'Low Stock'
                        ELSE 'In Stock'
                    END AS status
                FROM hardware 
                WHERE item_name LIKE ? OR category LIKE ?
                ORDER BY item_id ASC
            """
            search_pattern = f"%{search_term.strip()}%"
            cursor.execute(query, (search_pattern, search_pattern))
            records = cursor.fetchall()
            conn.close()
            return records
        except Exception as e:
            logger.error(f"Error fetching hardware records: {e}")
            return []

    def get_total_inventory_value(self):
        """Calculates total inventory valuation (quantity * unit_price)."""
        try:
            conn = db_connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute("SELECT SUM(quantity * unit_price) FROM hardware")
            result = cursor.fetchone()[0]
            conn.close()
            return result if result is not None else 0.0
        except Exception as e:
            logger.error(f"Error calculating total value: {e}")
            return 0.0

    def get_total_stocks(self):
        try:
            with db_connect(self.db_name) as conn:
                result = conn.execute(
                    "SELECT COALESCE(SUM(quantity), 0) FROM hardware").fetchone()
            return int(result[0])
        except Exception as e:
            logger.error(f"Error calculating total stocks: {e}")
            return 0

    def get_borrowed_items(self, student_id=None, student_name=None):
        try:
            with db_connect(self.db_name) as conn:
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
        except Exception as e:
            logger.error(f"Error fetching borrowed items: {e}")
            return []

    def get_history_records(self, student_name=None):
        """Return the complete audit trail, including rejected actions."""
        try:
            with db_connect(self.db_name) as conn:
                query = """
                    SELECT
                        history_id, actor_username, actor_role, action,
                        entity_type, entity_id, item_name, student_name,
                        student_id, quantity, status, details, created_at
                    FROM activity_history
                    WHERE 1 = 1
                """
                params = []
                if student_name:
                    query += " AND (actor_username = ? OR student_name = ? OR student_id = ?)"
                    params.extend([student_name, student_name, student_name])
                query += " ORDER BY history_id DESC"
                return conn.execute(query, params).fetchall()
        except Exception as e:
            logger.error(f"Error fetching activity history: {e}")
            return []

    def get_pending_borrow_requests(self):
        try:
            with db_connect(self.db_name) as conn:
                return conn.execute("""
                    SELECT b.request_id, h.item_name, b.student_name, b.student_id, b.quantity, b.created_at
                    FROM borrow_requests b JOIN hardware h ON h.item_id = b.item_id
                    WHERE b.status = 'Pending' ORDER BY b.request_id DESC
                """).fetchall()
        except Exception as e:
            logger.error(f"Error fetching borrow requests: {e}")
            return []

    def get_pending_return_requests(self):
        try:
            with db_connect(self.db_name) as conn:
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
        except Exception as e:
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
            with db_connect(self.db_name) as conn:
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
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO borrow_requests (item_id, student_id, student_name, quantity) VALUES (?, ?, ?, ?)",
                    (item_id, student_id, student_name, quantity)
                )
                request_id = getattr(cursor, "lastrowid", None)
                if request_id is None:
                    try:
                        request_id = conn.execute(
                            "SELECT request_id FROM borrow_requests WHERE item_id = ? AND student_id = ? AND student_name = ? ORDER BY request_id DESC LIMIT 1",
                            (item_id, student_id, student_name)
                        ).fetchone()[0]
                    except Exception:
                        request_id = None
            log_activity(
                self.db_name, actor_username=student_name, actor_role="USER",
                action="Borrow Request Submitted", entity_type="borrow_request",
                entity_id=request_id, item_name=None, student_name=student_name,
                student_id=student_id, quantity=quantity, status="Pending",
                details="Borrow request submitted for admin approval."
            )
            return True, "Borrow request submitted for approval."
        except (ValueError, sqlite3.Error) as e:
            return False, f"Borrow request failed: {e}"

    def approve_borrow_request(self, request_id, approve=True, actor_username='ADMIN'):
        try:
            with db_connect(self.db_name) as conn:
                row = conn.execute(
                    """
                    SELECT b.item_id, b.student_id, b.student_name, b.quantity, b.status,
                           h.item_name
                    FROM borrow_requests b
                    JOIN hardware h ON h.item_id = b.item_id
                    WHERE b.request_id = ?
                    """, (request_id,)).fetchone()
                if not row:
                    return False, "Borrow request not found."

                item_id, student_id, student_name, quantity, status, item_name = row
                if status != "Pending":
                    return False, "Borrow request has already been processed."

                new_status = "Approved" if approve else "Rejected"

                if approve:
                    stock = conn.execute(
                        "SELECT quantity FROM hardware WHERE item_id = ?", (item_id,)).fetchone()
                    if not stock or stock[0] < quantity:
                        return False, "Cannot approve: insufficient stock."

                    conn.execute(
                        """UPDATE hardware
                           SET quantity = quantity - ?,
                               status = CASE
                                   WHEN quantity - ? <= 0 THEN 'Out of Stock'
                                   WHEN quantity - ? < 10 THEN 'Low Stock'
                                   ELSE 'In Stock'
                               END
                           WHERE item_id = ?""",
                        (quantity, quantity, quantity, item_id)
                    )
                    for _ in range(quantity):
                        conn.execute(
                            """INSERT INTO asset_loans
                               (item_id, student_id, student_name, status)
                               VALUES (?, ?, ?, 'Active')""",
                            (item_id, student_id, student_name)
                        )

                conn.execute(
                    "UPDATE borrow_requests SET status = ? WHERE request_id = ?",
                    (new_status, request_id)
                )

            log_activity(
                self.db_name, actor_username=actor_username, actor_role="ADMIN",
                action=f"Borrow Request {new_status}",
                entity_type="borrow_request", entity_id=request_id,
                item_name=item_name, student_name=student_name,
                student_id=student_id, quantity=quantity, status=new_status,
                details=f"Administrator {'approved' if approve else 'rejected'} the borrow request."
            )
            return True, f"Borrow request {'approved' if approve else 'rejected'}."
        except Exception as e:
            logger.error(f"Borrow approval failed: {e}")
            return False, f"Borrow approval failed: {e}"

    def request_return(self, loan_id, student_id, student_name):
        try:
            with db_connect(self.db_name) as conn:
                loan = conn.execute(
                    "SELECT status, student_id, student_name FROM asset_loans WHERE loan_id = ?", (loan_id,)).fetchone()
                if not loan or loan[0] != 'Active' or loan[2] != student_name:
                    return False, "Active borrowed item not found."
                existing = conn.execute(
                    "SELECT 1 FROM return_requests WHERE loan_id = ? AND status = 'Pending'", (loan_id,)).fetchone()
                if existing:
                    return False, "A return request is already pending."
                conn.execute(
                    "INSERT INTO return_requests (loan_id, student_id) VALUES (?, ?)", (loan_id, student_id))
            return True, "Return request submitted for approval."
        except Exception as e:
            return False, f"Return request failed: {e}"

    def request_return_quantity(self, item_id, student_id, student_name, quantity):
        try:
            quantity = int(quantity)
            if quantity <= 0:
                return False, "Return quantity must be greater than zero."
            with db_connect(self.db_name) as conn:
                loans = conn.execute("""
                    SELECT l.loan_id
                    FROM asset_loans l
                    WHERE l.item_id = ? AND l.student_name = ? AND l.status = 'Active'
                    AND NOT EXISTS (
                        SELECT 1 FROM return_requests r
                        WHERE r.loan_id = l.loan_id AND r.status = 'Pending'
                    )
                    ORDER BY l.loan_id ASC LIMIT ?
                """, (item_id, student_name, quantity)).fetchall()
                if len(loans) < quantity:
                    return False, "That many items are unavailable for return."
                conn.executemany(
                    "INSERT INTO return_requests (loan_id, student_id) VALUES (?, ?)",
                    [(loan[0], student_id) for loan in loans],
                )
            log_activity(
                self.db_name, actor_username=student_name, actor_role="USER",
                action="Return Request Submitted", entity_type="return_request",
                item_name=None, student_name=student_name, student_id=student_id,
                quantity=quantity, status="Pending",
                details="Return request submitted for admin approval."
            )
            return True, f"Return request submitted for {quantity} item(s)."
        except (ValueError, sqlite3.Error) as e:
            return False, f"Return request failed: {e}"

    def approve_return_request(self, request_id, approve=True, actor_username='ADMIN'):
        try:
            with db_connect(self.db_name) as conn:
                row = conn.execute(
                    """
                    SELECT r.loan_id, r.status, l.item_id, l.student_name, r.student_id,
                           h.item_name
                    FROM return_requests r
                    JOIN asset_loans l ON l.loan_id = r.loan_id
                    JOIN hardware h ON h.item_id = l.item_id
                    WHERE r.request_id = ?
                    """, (request_id,)).fetchone()
                if not row or row[1] != "Pending":
                    return False, "Return request is unavailable."

                item_id, student_name, student_id, item_name = row[2], row[3], row[4], row[5]

                request_rows = conn.execute("""
                    SELECT r.request_id, r.loan_id
                    FROM return_requests r
                    JOIN asset_loans l ON l.loan_id = r.loan_id
                    WHERE r.status = 'Pending' AND l.item_id = ?
                      AND l.student_name = ? AND r.student_id = ?
                """, (item_id, student_name, student_id)).fetchall()

                loan_ids = [request[1] for request in request_rows]
                new_status = "Approved" if approve else "Rejected"

                if approve:
                    if not loan_ids:
                        return False, "Borrowed item is unavailable."

                    placeholders = ",".join("?" for _ in loan_ids)
                    active_count = conn.execute(
                        f"SELECT COUNT(*) FROM asset_loans WHERE loan_id IN ({placeholders}) AND status = 'Active'",
                        loan_ids
                    ).fetchone()[0]
                    if active_count != len(loan_ids):
                        return False, "Borrowed item is unavailable."

                    conn.execute(
                        f"UPDATE asset_loans SET status = 'Returned', return_time = CURRENT_TIMESTAMP WHERE loan_id IN ({placeholders})",
                        loan_ids
                    )
                    conn.execute(
                        """UPDATE hardware
                           SET quantity = quantity + ?,
                               status = CASE
                                   WHEN quantity + ? <= 0 THEN 'Out of Stock'
                                   WHEN quantity + ? < 10 THEN 'Low Stock'
                                   ELSE 'In Stock'
                               END
                           WHERE item_id = ?""",
                        (len(loan_ids), len(loan_ids), len(loan_ids), item_id)
                    )

                if request_rows:
                    conn.executemany(
                        "UPDATE return_requests SET status = ? WHERE request_id = ?",
                        [(new_status, request[0]) for request in request_rows]
                    )

            log_activity(
                self.db_name, actor_username=actor_username, actor_role="ADMIN",
                action=f"Return Request {new_status}",
                entity_type="return_request", entity_id=request_id,
                item_name=item_name, student_name=student_name,
                student_id=student_id, quantity=len(request_rows),
                status=new_status,
                details=f"Administrator {'approved' if approve else 'rejected'} the return request."
            )
            return True, f"Return request {'approved' if approve else 'rejected'} for {len(request_rows)} item(s)."
        except Exception as e:
            logger.error(f"Return approval failed: {e}")
            return False, f"Return approval failed: {e}"

    def add_hardware(self, name, category, quantity, unit_price, actor_username='ADMIN'):
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

            conn = db_connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO hardware (item_name, category, quantity, unit_price, status)
                VALUES (?, ?, ?, ?, ?)
            """, (name, category, qty, price, status))
            conn.commit()
            conn.close()
            logger.info(
                f"HARDWARE ADDED: '{name}' (Qty: {qty}, Price: {price})")
            log_activity(
                self.db_name, actor_username=actor_username, actor_role="ADMIN",
                action="Hardware Added", entity_type="hardware",
                item_name=name, quantity=qty, status=status,
                details=f"New inventory item added at unit price {price}."
            )
            return True, "Hardware item added successfully."
        except ValueError:
            return False, "Quantity must be an integer and price must be a number."
        except Exception as e:
            logger.error(f"Error adding hardware: {e}")
            return False, f"Database error: {e}"

    def update_hardware(self, item_id, new_quantity, new_price, actor_username='ADMIN'):
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

            conn = db_connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE hardware 
                SET quantity = ?, unit_price = ?, status = ?
                WHERE item_id = ?
            """, (qty, price, status, item_id))
            conn.commit()
            conn.close()
            logger.info(
                f"HARDWARE UPDATED: Item ID {item_id} -> Qty: {qty}, Price: {price}")
            log_activity(
                self.db_name, actor_username=actor_username, actor_role="ADMIN",
                action="Hardware Updated", entity_type="hardware",
                entity_id=item_id, quantity=qty, status=status,
                details=f"Inventory quantity/price updated. Unit price: {price}."
            )
            return True, "Item updated successfully."
        except ValueError:
            return False, "Quantity must be an integer and price must be a number."
        except Exception as e:
            logger.error(f"Error updating hardware: {e}")
            return False, f"Database error: {e}"

    def delete_hardware(self, item_id, actor_username='ADMIN'):
        """Deletes an item from the hardware table."""
        try:
            conn = db_connect(self.db_name)
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM hardware WHERE item_id = ?", (item_id,))
            conn.commit()
            conn.close()
            logger.info(f"HARDWARE DELETED: Item ID {item_id}")
            log_activity(
                self.db_name, actor_username=actor_username, actor_role="ADMIN",
                action="Hardware Deleted", entity_type="hardware",
                entity_id=item_id, status="Deleted",
                details="Inventory item deleted."
            )
            return True, "Item deleted successfully."
        except Exception as e:
            logger.error(f"Error deleting hardware: {e}")
            return False, f"Database error: {e}"

    # ---------------- MODULE 1: CHECK-IN / CHECK-OUT ----------------

    def checkout_item(self, item_id, student_id):
        """Decrements quantity by 1, updates status, and logs active loan."""
        if not student_id.strip():
            return False, "Student ID cannot be empty."

        try:
            conn = db_connect(self.db_name)
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
                INSERT INTO asset_loans (item_id, student_id, status)
                VALUES (?, ?, 'Active')
            """, (item_id, student_id.strip()))

            conn.commit()
            conn.close()
            logger.info(
                f"CHECKOUT EVENT: Item ID {item_id} issued to Student '{student_id}'. New Qty: {new_qty}")
            return True, "Item checked out successfully."
        except Exception as e:
            logger.error(f"Error during checkout: {e}")
            return False, f"Database error: {e}"

    def return_item(self, item_id):
        """Increments quantity by 1, updates status, and closes the active loan."""
        try:
            conn = db_connect(self.db_name)
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
                SET status = 'Returned', return_time = CURRENT_TIMESTAMP 
                WHERE loan_id = (
                    SELECT loan_id FROM asset_loans 
                    WHERE item_id = ? AND status = 'Active' 
                    ORDER BY loan_id DESC LIMIT 1
                )
            """, (item_id,))

            conn.commit()
            conn.close()
            logger.info(
                f"RETURN EVENT: Item ID {item_id} returned. New Qty: {new_qty}")
            return True, "Item returned successfully."
        except Exception as e:
            logger.error(f"Error during return: {e}")
            return False, f"Database error: {e}"

    def fetch_catalog_with_availability(self):
        """
        Fetches catalog items and computes Total Qty, Active Reserved Qty, and Available Qty.
        Available Qty = Total Qty - (Approved or Pending Reservations)
        """
        try:
            conn = db_connect(self.db_name)
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
        except Exception as e:
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
                conn = db_connect(self.db_name)
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

            # Close local connection if created dynamically
            if hasattr(conn, 'close') and not hasattr(self, 'db'):
                conn.close()

            log_activity(
                self.db_name, actor_username=student_id, actor_role="USER",
                action="Reservation Submitted", entity_type="reservation",
                entity_id=None, student_id=student_id, status="Pending",
                details=f"Reservation submitted from {start_time} to {end_time}."
            )
            return True, "Reservation request submitted for approval!"

        except Exception as e:
            print(f"Database insertion error: {e}")
            return False, f"Database error: {str(e)}"

    def fetch_all_reservations(self):
        """Fetches active reservation requests joined with item details."""
        try:
            conn = db_connect(self.db_name)
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
        except Exception as e:
            logger.error(f"Error fetching reservations: {e}")
            return []

    def update_reservation_status(self, reservation_id, status, actor_username='ADMIN'):
        """
        Updates status ('Approved' or 'Rejected') for admin review.
        Decrements hardware stock on approval and resets 'notified' flag to 0.
        """
        try:
            conn = db_connect(self.db_name)
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

            logger.info(
                f"RESERVATION STATUS UPDATED: ID {reservation_id} set to '{target_status}'."
            )
            log_activity(
                self.db_name, actor_username=actor_username, actor_role="ADMIN",
                action=f"Reservation {target_status}", entity_type="reservation",
                entity_id=reservation_id, status=target_status,
                details=f"Administrator changed reservation status to {target_status}."
            )
            return True, f"Reservation status updated to '{target_status}'."

        except Exception as e:
            logger.error(f"Error updating reservation status: {e}")
            return False, f"Database error: {e}"

    def check_user_notifications(self, student_id):
        """
        Fetches unread notifications for a user upon login and marks them as read (notified = 1).
        """
        notifications = []
        try:
            conn = db_connect(self.db_name)
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
        except Exception as e:
            logger.error(f"Error retrieving user notifications: {e}")

        return notifications

    def delete_reservation(self, reservation_id):
        """Deletes a reservation entry from the database table."""
        try:
            conn = db_connect(self.db_name)
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
        except Exception as e:
            logger.error(f"Error deleting reservation: {e}")
            return False, f"Database error: {e}"

    # ---------------- MODULE 3: LOGBOOK EXPORT ----------------

    def export_to_csv(self, filename="inventory_report.csv"):
        """Exports complete active loan usage history to CSV file."""
        try:
            conn = db_connect(self.db_name)
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
