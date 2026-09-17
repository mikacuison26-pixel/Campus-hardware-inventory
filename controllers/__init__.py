def init_db(self):
    """Ensures the users table exists and contains the email column."""
    conn = sqlite3.connect(self.db_name)
    cursor = conn.cursor()

    # 1. Create table if it doesn't exist
    cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
        """)

    # 2. Safely add 'email' column without UNIQUE constraint for existing databases
    cursor.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'email' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN email TEXT")
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)")

    conn.commit()
    conn.close()
