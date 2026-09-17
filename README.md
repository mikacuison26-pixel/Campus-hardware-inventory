# Campus Hardware Inventory System

A Flask-based laboratory equipment management system for students and administrators.

## Features

- Student login and registration
- Password reset flow with show/hide password toggle
- Hardware catalog with search
- Borrow request flow with quantity and student ID
- Return request flow for active borrowed items
- Admin catalog management for adding and updating items
- Admin request management for borrow approvals, return approvals, and password resets
- Borrow history and activity tracking
- Pink-themed responsive UI

## Tech Stack

- Python
- Flask
- SQLite
- Jinja2
- bcrypt

## Project Structure

- `app.py` – main Flask application and routes
- `controllers/` – business logic for auth and hardware actions
- `models/` – database initialization and schema
- `templates/` – HTML pages
- `static/` – CSS styling
- `hardware_inventory.db` – SQLite database

## Setup

1. Open the project folder in a terminal.
2. Create and activate a virtual environment if needed.
3. Install dependencies:

```powershell
pip install -r requirements.txt
```

## Run the app

On Windows:

```powershell
.\.venv\Scripts\python.exe app.py
```

Then open:

```text
http://127.0.0.1:5000
```

## Default access

- Student login: use a user account created from the registration page
- Admin login: create an admin account through the registration page and set role to `ADMIN`

## Migration to PostgreSQL

This project can be migrated from the local SQLite database to PostgreSQL using the script `migrate_sqlite_to_postgres.py`.

1. Add your PostgreSQL connection string in a local `.env` file as `DATABASE_URL`.
2. Keep the SQLite database file `hardware_inventory.db` in the project folder.
3. Run:

```powershell
.\.venv\Scripts\python.exe migrate_sqlite_to_postgres.py
```

The script copies the project tables and data from SQLite into PostgreSQL so records do not need to be recreated manually.

## Notes

- The app uses SQLite and will create the database automatically on startup.
- Flask runs in debug mode by default for development.
