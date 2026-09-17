import os
import sqlite3
from pathlib import Path

import psycopg
from psycopg import sql
from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR / ".env")

SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", str(PROJECT_DIR / "hardware_inventory.db"))
DATABASE_URL = os.getenv("DATABASE_URL")

TABLES = [
    "users",
    "password_resets",
    "hardware",
    "asset_loans",
    "reservations",
    "borrow_requests",
    "return_requests",
]


def sqlite_connect(db_path: str):
    return sqlite3.connect(db_path)


def pg_type(sqlite_type: str) -> str:
    sqlite_type = (sqlite_type or "TEXT").upper()
    if "INT" in sqlite_type:
        return "INTEGER"
    if "REAL" in sqlite_type or "FLOAT" in sqlite_type or "DOUBLE" in sqlite_type:
        return "DOUBLE PRECISION"
    if "BLOB" in sqlite_type:
        return "BYTEA"
    if "TIMESTAMP" in sqlite_type:
        return "TIMESTAMP"
    return "TEXT"


def default_sqlite_to_postgres(value):
    if value is None:
        return None
    value = str(value).strip()
    if value.upper() in {"CURRENT_TIMESTAMP", "CURRENT_DATE"}:
        return value.upper()
    if value.startswith("'") and value.endswith("'"):
        return value
    if value.lower() in {"true", "false"}:
        return value.upper()
    try:
        int(value)
        return value
    except ValueError:
        pass
    try:
        float(value)
        return value
    except ValueError:
        pass
    return "'" + value.replace("'", "''") + "'"


def get_columns(conn: sqlite3.Connection, table: str):
    rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    columns = []
    for row in rows:
        cid, name, sqlite_type, notnull, default_value, pk = row
        columns.append({
            "name": name,
            "type": pg_type(sqlite_type),
            "notnull": bool(notnull),
            "default": default_sqlite_to_postgres(default_value) if default_value is not None else None,
            "pk": bool(pk),
        })
    return columns


def create_table_in_postgres(cur, table: str, columns):
    parts = []
    pk_columns = [col["name"] for col in columns if col["pk"]]

    for col in columns:
        name = col["name"]
        dtype = col["type"]
        line = f'"{name}" {dtype}'
        if col["pk"]:
            line += " PRIMARY KEY"
        elif col["notnull"]:
            line += " NOT NULL"
        if col["default"] is not None:
            line += f" DEFAULT {col['default']}"
        parts.append(line)

    create_sql = f'CREATE TABLE IF NOT EXISTS "{table}" (\n    ' + ",\n    ".join(
        parts) + "\n);"
    cur.execute(create_sql)


def migrate_table(sqlite_conn: sqlite3.Connection, pg_conn, table: str):
    columns = get_columns(sqlite_conn, table)
    if not columns:
        print(f"Skipping {table}: no table found in SQLite.")
        return

    with pg_conn.cursor() as cur:
        create_table_in_postgres(cur, table, columns)

        column_names = [col["name"] for col in columns]
        quoted_names = ', '.join(f'"{name}"' for name in column_names)
        placeholders = ', '.join(['%s'] * len(column_names))

        sqlite_rows = sqlite_conn.execute(
            f'SELECT * FROM "{table}"').fetchall()
        if sqlite_rows:
            insert_sql = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                sql.Identifier(table),
                sql.SQL(', ').join(sql.Identifier(name)
                                   for name in column_names),
                sql.SQL(', ').join(sql.Placeholder() for _ in column_names),
            )
            cur.executemany(insert_sql, sqlite_rows)

    pg_conn.commit()
    print(f"Migrated {table}: {len(sqlite_rows)} row(s)")


def main():
    if not DATABASE_URL or DATABASE_URL == "YOUR_SUPABASE_CONNECTION_STRING":
        raise RuntimeError(
            "DATABASE_URL is missing or still uses the placeholder. Add your real Supabase "
            "connection string to .env, then run this migration again.")

    sqlite_conn = sqlite_connect(SQLITE_DB_PATH)
    try:
        sqlite_conn.row_factory = sqlite3.Row
        pg_conn = psycopg.connect(DATABASE_URL)
        try:
            for table in TABLES:
                if table in [row[0] for row in sqlite_conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]:
                    migrate_table(sqlite_conn, pg_conn, table)
                else:
                    print(f"Skipping {table}: not found in SQLite database.")
        finally:
            pg_conn.close()
    finally:
        sqlite_conn.close()


if __name__ == "__main__":
    main()
