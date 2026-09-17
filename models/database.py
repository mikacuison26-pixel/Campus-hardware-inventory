from logger import logger
import sqlite3
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))


def init_db(db_name="hardware_inventory.db"):
    try:
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()

        # 1. Users Table (with Role, Lock status, and Failed Attempts)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'USER',
                failed_attempts INTEGER NOT NULL DEFAULT 0,
                is_locked INTEGER NOT NULL DEFAULT 0
            )
        """)

        # 2. Password Resets Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS password_resets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                email TEXT NOT NULL,
                desired_password_hash TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING'
            )
        """)

        # 3. Hardware Catalog Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hardware (
                item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT NOT NULL,
                category TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price REAL NOT NULL,
                status TEXT NOT NULL
            )
        """)

        # 4. Active Loans & Usage Logbook Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS asset_loans (
                loan_id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER REFERENCES hardware(item_id),
                student_id TEXT NOT NULL,
                student_name TEXT,
                checkout_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                return_time TIMESTAMP,
                status TEXT DEFAULT 'Active'
            )
        """)

        # 5. Time-Slot Reservations Table (with Status and Notification tracking)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                reservation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER REFERENCES hardware(item_id),
                student_id TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                status TEXT DEFAULT 'Pending',
                notified INTEGER DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS borrow_requests (
                request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER REFERENCES hardware(item_id),
                student_id TEXT NOT NULL,
                student_name TEXT,
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                status TEXT NOT NULL DEFAULT 'Pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS return_requests (
                request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                loan_id INTEGER REFERENCES asset_loans(loan_id),
                student_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Auto-migration: Check and add missing columns to 'reservations' if database exists
        cursor.execute("PRAGMA table_info(reservations)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'status' not in columns:
            cursor.execute(
                "ALTER TABLE reservations ADD COLUMN status TEXT DEFAULT 'Pending'")
            logger.info(
                "Migrated 'reservations' table: added missing 'status' column.")

        if 'notified' not in columns:
            cursor.execute(
                "ALTER TABLE reservations ADD COLUMN notified INTEGER DEFAULT 0")
            logger.info(
                "Migrated 'reservations' table: added missing 'notified' column.")

        for table in ('asset_loans', 'borrow_requests'):
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [col[1] for col in cursor.fetchall()]
            if 'student_name' not in columns:
                cursor.execute(
                    f"ALTER TABLE {table} ADD COLUMN student_name TEXT")
                cursor.execute(
                    f"UPDATE {table} SET student_name = student_id WHERE student_name IS NULL")

        conn.commit()
        conn.close()
        logger.info("Database and all tables initialized successfully.")
    except sqlite3.Error as e:
        logger.error(f"Database setup error: {e}")
